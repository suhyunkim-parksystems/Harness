from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.config import settings
from app.models.market import AssetCategory, ChartResponse, SearchCandidate, SearchResponse, StockDetail
from app.providers.krx_provider import KRXProvider, MasterRecord
from app.providers.nasdaq_provider import NasdaqMasterRecord, NasdaqProvider
from app.providers.yahoo_finance import YahooFinanceProvider
from app.services.cache import MemoryCache


logger = logging.getLogger(__name__)


class _MasterEntry:
    """Unified internal symbol master entry."""

    __slots__ = ("id", "symbol", "name", "exchange", "market", "asset_type", "currency")

    def __init__(
        self,
        id: str,
        symbol: str,
        name: str,
        exchange: str,
        market: str,
        asset_type: str,
        currency: str,
    ) -> None:
        self.id = id
        self.symbol = symbol
        self.name = name
        self.exchange = exchange
        self.market = market
        self.asset_type = asset_type
        self.currency = currency


class SearchService:
    def __init__(
        self,
        krx_provider: KRXProvider | None = None,
        nasdaq_provider: NasdaqProvider | None = None,
        yahoo_provider: YahooFinanceProvider | None = None,
        master_ttl_seconds: int | None = None,
        quote_ttl_seconds: int | None = None,
    ) -> None:
        _master_ttl = master_ttl_seconds if master_ttl_seconds is not None else settings.symbol_master_ttl_seconds
        _quote_ttl = quote_ttl_seconds if quote_ttl_seconds is not None else settings.quote_cache_ttl_seconds

        self.krx_provider = krx_provider or KRXProvider(timeout=settings.stock_provider_timeout_seconds)
        self.nasdaq_provider = nasdaq_provider or NasdaqProvider(timeout=settings.stock_provider_timeout_seconds)
        self.yahoo_provider = yahoo_provider or YahooFinanceProvider(timeout=settings.stock_provider_timeout_seconds)

        self._master_cache: MemoryCache[list[_MasterEntry]] = MemoryCache(ttl_seconds=_master_ttl)
        self._detail_cache: MemoryCache[StockDetail] = MemoryCache(ttl_seconds=_quote_ttl)
        self._chart_cache: MemoryCache[ChartResponse] = MemoryCache(ttl_seconds=_quote_ttl)
        self._load_lock = asyncio.Lock()

    async def preload_all_masters(self) -> None:
        """Pre-fetch all master lists into cache. Called at startup."""
        for category in ("kr_stock", "kr_etf", "us_stock", "us_etf"):
            try:
                await self._ensure_master_loaded(category)  # type: ignore[arg-type]
            except Exception as exc:
                logger.warning("Preload failed for %s: %s", category, exc)

    async def search(self, query: str, category: AssetCategory) -> SearchResponse:
        """Return up to 10 autocomplete candidates matching query."""
        master = await self._ensure_master_loaded(category)
        q = query.lower().strip()
        # Korean stocks/ETFs are searchable by both name and 6-digit code; US
        # symbols match by ticker only.
        is_korean = category in ("kr_stock", "kr_etf")

        prefix_matches: list[_MasterEntry] = []
        substring_matches: list[_MasterEntry] = []
        seen: set[str] = set()

        for entry in master:
            if entry.id in seen:
                continue
            keys = (
                (entry.name.lower(), entry.symbol.lower())
                if is_korean
                else (entry.symbol.lower(),)
            )
            if any(key.startswith(q) for key in keys):
                prefix_matches.append(entry)
                seen.add(entry.id)
            elif any(q in key for key in keys):
                substring_matches.append(entry)
                seen.add(entry.id)
            if len(prefix_matches) >= 10:
                break

        results = (prefix_matches + substring_matches)[:10]
        return SearchResponse(
            candidates=[_to_candidate(e) for e in results],
            status="ok",
            as_of=datetime.now(timezone.utc),
        )

    async def get_detail(self, symbol: str, category: AssetCategory) -> StockDetail:
        """Fetch symbol detail with cache and stale fallback."""
        cache_key = f"detail:{category}:{symbol}"
        cached = self._detail_cache.get(cache_key)
        if cached is not None:
            return cached

        entry = self._find_master_entry(symbol, category)
        market = entry.market if entry else ""
        asset_type = entry.asset_type if entry else category

        try:
            detail = await self.yahoo_provider.fetch_detail(symbol, market=market, asset_type=asset_type)
            if detail.status == "unavailable":
                stale = self._detail_cache.get_stale(cache_key)
                if stale is not None:
                    return stale.model_copy(update={"status": "stale", "error_message": "캐시된 데이터를 사용합니다."})
                return detail  # no stale data; return unavailable as-is without caching
            self._detail_cache.set(cache_key, detail)
            return detail
        except Exception as exc:
            stale = self._detail_cache.get_stale(cache_key)
            if stale is not None:
                return stale.model_copy(update={"status": "stale", "error_message": "캐시된 데이터를 사용합니다."})
            logger.warning("Detail fetch failed for %s: %s", symbol, exc)
            raise

    async def get_chart(self, symbol: str, period: str, category: AssetCategory) -> ChartResponse:
        """Fetch chart data with cache and stale fallback."""
        cache_key = f"chart:{category}:{symbol}:{period}"
        cached = self._chart_cache.get(cache_key)
        if cached is not None:
            return cached

        entry = self._find_master_entry(symbol, category)
        market = entry.market if entry else ""
        asset_type = entry.asset_type if entry else category

        try:
            chart = await self.yahoo_provider.fetch_chart(symbol, period, market=market, asset_type=asset_type)
            if chart.status == "unavailable":
                stale = self._chart_cache.get_stale(cache_key)
                if stale is not None:
                    return stale.model_copy(update={"status": "stale", "error_message": "캐시된 차트 데이터를 사용합니다."})
                return chart  # no stale data; return unavailable as-is without caching
            self._chart_cache.set(cache_key, chart)
            return chart
        except Exception as exc:
            stale = self._chart_cache.get_stale(cache_key)
            if stale is not None:
                return stale.model_copy(update={"status": "stale", "error_message": "캐시된 차트 데이터를 사용합니다."})
            logger.warning("Chart fetch failed for %s: %s", symbol, exc)
            raise

    async def _ensure_master_loaded(self, category: AssetCategory) -> list[_MasterEntry]:
        cached = self._master_cache.get(category)
        if cached is not None:
            return cached

        async with self._load_lock:
            cached = self._master_cache.get(category)
            if cached is not None:
                return cached

            if category in ("us_stock", "us_etf"):
                await self._load_us_masters()
            else:
                master = await self._load_kr_master(category)
                if master:
                    self._master_cache.set(category, master)
                else:
                    # Distinguish "master failed to load / parsed empty" from a
                    # normal search that simply has zero matches. An empty master
                    # here means the KRX fetch or CSV parse produced nothing.
                    logger.warning(
                        "KR master for %s loaded empty; KRX fetch or CSV parse "
                        "likely failed (search will return no candidates)",
                        category,
                    )

            return self._master_cache.get(category) or []

    async def _load_kr_master(self, category: AssetCategory) -> list[_MasterEntry]:
        if category == "kr_stock":
            records = await self.krx_provider.fetch_stock_master()
            return [_krx_to_entry(r, "kr_stock") for r in records]
        records = await self.krx_provider.fetch_etf_master()
        return [_krx_to_entry(r, "kr_etf") for r in records]

    async def _load_us_masters(self) -> None:
        """Load both us_stock and us_etf in a single NASDAQ request."""
        stocks_raw, etfs_raw = await self.nasdaq_provider.fetch_us_master()
        stocks = [_nasdaq_to_entry(r) for r in stocks_raw]
        etfs = [_nasdaq_to_entry(r) for r in etfs_raw]
        if stocks:
            self._master_cache.set("us_stock", stocks)
        if etfs:
            self._master_cache.set("us_etf", etfs)

    def _find_master_entry(self, symbol: str, category: AssetCategory) -> _MasterEntry | None:
        master = self._master_cache.get(category) or []
        sym_upper = symbol.upper()
        for entry in master:
            if entry.symbol.upper() == sym_upper:
                return entry
        return None


def _krx_to_entry(r: MasterRecord, asset_type: str) -> _MasterEntry:
    return _MasterEntry(
        id=f"krx:{r.code}",
        symbol=r.code,
        name=r.name,
        exchange="KRX",
        market=r.market,
        asset_type=asset_type,
        currency="KRW",
    )


def _nasdaq_to_entry(r: NasdaqMasterRecord) -> _MasterEntry:
    asset_type = "us_etf" if r.asset_type == "etf" else "us_stock"
    return _MasterEntry(
        id=f"us:{r.symbol}",
        symbol=r.symbol,
        name=r.name,
        exchange=r.exchange,
        market="US",
        asset_type=asset_type,
        currency="USD",
    )


def _to_candidate(e: _MasterEntry) -> SearchCandidate:
    return SearchCandidate(
        id=e.id,
        market=e.market,
        asset_type=e.asset_type,
        symbol=e.symbol,
        name=e.name,
        exchange=e.exchange,
        currency=e.currency,
        match_text=f"{e.symbol} {e.name}",
        source="KRX" if e.currency == "KRW" else "NASDAQ",
        status="ok",
    )
