from datetime import datetime, timezone

from app.providers.stooq import ProviderQuote
from app.services.market_service import MarketService
import pytest


pytestmark = pytest.mark.asyncio


def quote(symbol: str, value: float = 100.0) -> ProviderQuote:
    return ProviderQuote(
        symbol=symbol.upper(),
        value=value,
        change=1.0,
        change_percent=1.0,
        as_of=datetime(2026, 6, 4, tzinfo=timezone.utc),
        source="TestProvider",
    )


class FakeStooqProvider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    async def fetch_quotes(self, symbols):
        self.calls += 1
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeFrankfurterProvider:
    def __init__(self, response=None):
        self.response = response or {}
        self.calls = 0

    async def fetch_rates(self, pairs):
        self.calls += 1
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


async def test_market_service_uses_cache_for_repeated_summary_calls():
    stooq_provider = FakeStooqProvider([{symbol: quote(symbol) for symbol in ["^SPX", "^NDX", "^DJI", "^KOSPI", "^NKX", "^DAX", "^UKX", "^SHC", "^HSI", "USDKRW", "USDJPY", "EURUSD", "USDCNY", "GBPUSD"]}])
    service = MarketService(
        stooq_provider=stooq_provider,
        frankfurter_provider=FakeFrankfurterProvider(),
        cache_ttl_seconds=30,
    )

    first = await service.get_summary()
    second = await service.get_summary()

    assert first is second
    assert stooq_provider.calls == 1


async def test_market_service_marks_missing_items_and_uses_fx_fallback():
    stooq_provider = FakeStooqProvider([{"^SPX": quote("^SPX"), "USDKRW": quote("USDKRW")}])
    frankfurter_provider = FakeFrankfurterProvider({"EURUSD": quote("EURUSD", value=1.1)})
    service = MarketService(
        stooq_provider=stooq_provider,
        frankfurter_provider=frankfurter_provider,
        cache_ttl_seconds=30,
    )

    summary = await service.get_summary()

    assert summary.status == "partial"
    assert next(item for item in summary.indices if item.id == "sp500").status == "ok"
    assert next(item for item in summary.indices if item.id == "nasdaq100").status == "unavailable"
    eur_usd = next(item for item in summary.exchange_rates if item.id == "eur_usd")
    assert eur_usd.status == "stale"
    assert eur_usd.source == "Frankfurter daily fallback"
    assert next(item for item in summary.indices if item.id == "nasdaq100").source == "N/A"


async def test_market_service_continues_when_stooq_provider_raises():
    stooq_provider = FakeStooqProvider([TimeoutError("stooq timeout")])
    frankfurter_provider = FakeFrankfurterProvider({"USDKRW": quote("USDKRW", value=1300.0)})
    service = MarketService(
        stooq_provider=stooq_provider,
        frankfurter_provider=frankfurter_provider,
        cache_ttl_seconds=30,
    )

    summary = await service.get_summary()

    assert summary.status == "partial"
    assert frankfurter_provider.calls == 1
    assert next(item for item in summary.indices if item.id == "sp500").status == "unavailable"
    assert next(item for item in summary.indices if item.id == "sp500").source == "N/A"
    usd_krw = next(item for item in summary.exchange_rates if item.id == "usd_krw")
    assert usd_krw.status == "stale"
    assert usd_krw.source == "Frankfurter daily fallback"


async def test_market_service_continues_when_frankfurter_provider_raises():
    stooq_provider = FakeStooqProvider([{"^SPX": quote("^SPX")}])
    frankfurter_provider = FakeFrankfurterProvider(TimeoutError("frankfurter timeout"))
    service = MarketService(
        stooq_provider=stooq_provider,
        frankfurter_provider=frankfurter_provider,
        cache_ttl_seconds=30,
    )

    summary = await service.get_summary()

    assert summary.status == "partial"
    assert next(item for item in summary.indices if item.id == "sp500").status == "ok"
    usd_krw = next(item for item in summary.exchange_rates if item.id == "usd_krw")
    assert usd_krw.status == "unavailable"
    assert usd_krw.source == "N/A"


async def test_market_service_returns_stale_cache_after_refresh_failure():
    stooq_provider = FakeStooqProvider([
        {"^SPX": quote("^SPX")},
        RuntimeError("provider down"),
    ])
    service = MarketService(
        stooq_provider=stooq_provider,
        frankfurter_provider=FakeFrankfurterProvider(),
        cache_ttl_seconds=0,
    )

    first = await service.get_summary()
    second = await service.get_summary()

    assert first.indices[0].status == "ok"
    assert second.indices[0].status == "stale"
    assert second.indices[0].error_message == "최신 공급자 호출에 실패해 최근 캐시 값을 표시합니다."
