from __future__ import annotations

import logging
from collections.abc import Awaitable
from datetime import datetime, timezone

from app.config import settings
from app.models.market import MarketCollection, MarketItem, MarketSummary, SummaryStatus
from app.providers.frankfurter import FrankfurterProvider
from app.providers.stooq import ProviderQuote, StooqProvider
from app.providers.symbols import EXCHANGE_RATE_SYMBOLS, INDEX_SYMBOLS, ExchangeRateSymbol, MarketSymbol
from app.services.cache import MemoryCache


logger = logging.getLogger(__name__)


class MarketService:
    def __init__(
        self,
        stooq_provider: StooqProvider | None = None,
        frankfurter_provider: FrankfurterProvider | None = None,
        cache: MemoryCache[MarketSummary] | None = None,
        cache_ttl_seconds: int | None = None,
    ) -> None:
        self.cache_ttl_seconds = (
            settings.cache_ttl_seconds if cache_ttl_seconds is None else cache_ttl_seconds
        )
        self.stooq_provider = stooq_provider or StooqProvider()
        self.frankfurter_provider = frankfurter_provider or FrankfurterProvider()
        self.cache = cache or MemoryCache[MarketSummary](self.cache_ttl_seconds)

    async def get_summary(self, force_refresh: bool = False) -> MarketSummary:
        if not force_refresh:
            cached_summary = self.cache.get("market-summary")
            if cached_summary is not None:
                return cached_summary

        try:
            summary = await self._fetch_summary()
            if summary.status == "unavailable":
                stale_summary = self.cache.get_stale("market-summary")
                if stale_summary is not None:
                    return _mark_summary_stale(stale_summary)
            self.cache.set("market-summary", summary)
            return summary
        except Exception:
            stale_summary = self.cache.get_stale("market-summary")
            if stale_summary is not None:
                return _mark_summary_stale(stale_summary)
            raise

    async def get_indices(self) -> MarketCollection:
        summary = await self.get_summary()
        return MarketCollection(
            generated_at=summary.generated_at,
            cache_ttl_seconds=summary.cache_ttl_seconds,
            status=_to_collection_status(summary.indices),
            items=summary.indices,
        )

    async def get_exchange_rates(self) -> MarketCollection:
        summary = await self.get_summary()
        return MarketCollection(
            generated_at=summary.generated_at,
            cache_ttl_seconds=summary.cache_ttl_seconds,
            status=_to_collection_status(summary.exchange_rates),
            items=summary.exchange_rates,
        )

    async def _fetch_summary(self) -> MarketSummary:
        stooq_symbols = [symbol.symbol for symbol in INDEX_SYMBOLS + EXCHANGE_RATE_SYMBOLS]
        stooq_quotes = await _fetch_provider_quotes(
            "Stooq",
            self.stooq_provider.fetch_quotes(stooq_symbols),
        )
        fallback_pairs = [
            pair for pair in EXCHANGE_RATE_SYMBOLS if pair.symbol.upper() not in stooq_quotes
        ]
        frankfurter_quotes = await _fetch_provider_quotes(
            "Frankfurter",
            self.frankfurter_provider.fetch_rates(fallback_pairs),
        )

        indices = [
            _to_market_item(symbol, stooq_quotes.get(symbol.symbol.upper()), fallback_source=None)
            for symbol in INDEX_SYMBOLS
        ]
        exchange_rates = [
            _to_exchange_item(symbol, stooq_quotes, frankfurter_quotes)
            for symbol in EXCHANGE_RATE_SYMBOLS
        ]

        return MarketSummary(
            generated_at=datetime.now(timezone.utc),
            cache_ttl_seconds=self.cache_ttl_seconds,
            status=_to_collection_status(indices + exchange_rates),
            indices=indices,
            exchange_rates=exchange_rates,
        )


async def _fetch_provider_quotes(
    provider_name: str,
    request: Awaitable[dict[str, ProviderQuote]],
) -> dict[str, ProviderQuote]:
    try:
        return await request
    except Exception as exc:
        logger.warning("%s provider request failed: %s", provider_name, exc)
        return {}


def _to_exchange_item(
    symbol: ExchangeRateSymbol,
    stooq_quotes: dict[str, ProviderQuote],
    frankfurter_quotes: dict[str, ProviderQuote],
) -> MarketItem:
    stooq_quote = stooq_quotes.get(symbol.symbol.upper())
    if stooq_quote is not None:
        return _to_market_item(symbol, stooq_quote, fallback_source=None)

    frankfurter_quote = frankfurter_quotes.get(symbol.symbol.upper())
    if frankfurter_quote is not None:
        return _to_market_item(symbol, frankfurter_quote, fallback_source="Frankfurter daily fallback")

    return _to_market_item(symbol, None, fallback_source=None)


def _to_market_item(
    symbol: MarketSymbol,
    quote: ProviderQuote | None,
    fallback_source: str | None,
) -> MarketItem:
    if quote is None:
        return MarketItem(
            id=symbol.id,
            name=symbol.name,
            category=symbol.category,
            region=symbol.region,
            symbol=symbol.symbol,
            value=None,
            change=None,
            change_percent=None,
            currency=symbol.currency,
            as_of=None,
            source="N/A",
            status="unavailable",
            error_message="무료 데이터 공급자에서 유효한 값을 받지 못했습니다.",
        )

    status = "stale" if fallback_source or quote.change is None else "ok"
    return MarketItem(
        id=symbol.id,
        name=symbol.name,
        category=symbol.category,
        region=symbol.region,
        symbol=symbol.symbol,
        value=quote.value,
        change=quote.change,
        change_percent=quote.change_percent,
        currency=symbol.currency,
        as_of=quote.as_of,
        source=fallback_source or quote.source,
        status=status,
        error_message="일간 기준 무료 환율 fallback 값입니다." if fallback_source else None,
    )


def _to_collection_status(items: list[MarketItem]) -> SummaryStatus:
    unavailable_count = sum(1 for item in items if item.status == "unavailable")
    stale_count = sum(1 for item in items if item.status == "stale")
    if unavailable_count == len(items):
        return "unavailable"
    if unavailable_count or stale_count:
        return "partial"
    return "ok"


def _mark_summary_stale(summary: MarketSummary) -> MarketSummary:
    return summary.model_copy(
        update={
            "status": "partial",
            "indices": [_mark_item_stale(item) for item in summary.indices],
            "exchange_rates": [_mark_item_stale(item) for item in summary.exchange_rates],
        },
        deep=True,
    )


def _mark_item_stale(item: MarketItem) -> MarketItem:
    if item.status == "unavailable":
        return item
    return item.model_copy(
        update={
            "status": "stale",
            "error_message": "최신 공급자 호출에 실패해 최근 캐시 값을 표시합니다.",
        }
    )
