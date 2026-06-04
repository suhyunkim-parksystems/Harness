from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.market import ChartBar, ChartResponse, SearchCandidate, StockDetail
from app.providers.krx_provider import KRXProvider, MasterRecord
from app.providers.nasdaq_provider import NasdaqMasterRecord, NasdaqProvider
from app.providers.yahoo_finance import YahooFinanceProvider
from app.services.search_service import SearchService


def make_krx_stocks() -> list[MasterRecord]:
    return [
        MasterRecord("005930", "삼성전자", "KOSPI", "stock"),
        MasterRecord("000660", "SK하이닉스", "KOSPI", "stock"),
        MasterRecord("035720", "카카오", "KOSDAQ", "stock"),
        MasterRecord("035420", "삼성SDS", "KOSPI", "stock"),
    ]


def make_nasdaq_masters() -> tuple[list, list]:
    stocks = [
        NasdaqMasterRecord("AAPL", "Apple Inc.", "NASDAQ", "stock"),
        NasdaqMasterRecord("AMZN", "Amazon.com Inc.", "NASDAQ", "stock"),
        NasdaqMasterRecord("AAON", "AAON Inc.", "NASDAQ", "stock"),
    ]
    etfs = [
        NasdaqMasterRecord("SPY", "SPDR S&P 500 ETF", "NYSE Arca", "etf"),
    ]
    return stocks, etfs


def make_stock_detail(symbol: str = "005930") -> StockDetail:
    return StockDetail(
        symbol=symbol,
        name="삼성전자",
        market="KOSPI",
        asset_type="한국주식",
        exchange="KRX",
        currency="KRW",
        current_price=70000.0,
        open_price=69500.0,
        high_price=70500.0,
        low_price=69000.0,
        prev_close=69800.0,
        change=200.0,
        change_percent=0.29,
        volume=10000000,
        as_of=datetime(2026, 6, 4, tzinfo=timezone.utc),
        source="Yahoo Finance",
        status="ok",
        error_message=None,
    )


def make_chart_response(symbol: str = "005930") -> ChartResponse:
    return ChartResponse(
        symbol=symbol,
        period="1m",
        bars=[ChartBar(timestamp="2026-06-04", open=69500.0, high=70500.0, low=69000.0, close=70000.0, volume=10000000)],
        source="Yahoo Finance",
        status="ok",
        error_message=None,
    )


def build_service(
    krx_stocks: list[MasterRecord] | None = None,
    nasdaq_masters: tuple | None = None,
    detail: StockDetail | None = None,
    chart: ChartResponse | None = None,
) -> SearchService:
    krx_mock = MagicMock(spec=KRXProvider)
    krx_mock.fetch_stock_master = AsyncMock(return_value=krx_stocks or make_krx_stocks())
    krx_mock.fetch_etf_master = AsyncMock(return_value=[])

    nasdaq_mock = MagicMock(spec=NasdaqProvider)
    nasdaq_mock.fetch_us_master = AsyncMock(return_value=nasdaq_masters or make_nasdaq_masters())

    yahoo_mock = MagicMock(spec=YahooFinanceProvider)
    yahoo_mock.fetch_detail = AsyncMock(return_value=detail or make_stock_detail())
    yahoo_mock.fetch_chart = AsyncMock(return_value=chart or make_chart_response())

    return SearchService(
        krx_provider=krx_mock,
        nasdaq_provider=nasdaq_mock,
        yahoo_provider=yahoo_mock,
        master_ttl_seconds=60,
        quote_ttl_seconds=10,
    )


@pytest.mark.asyncio
async def test_search_prefix_matches_ranked_before_substring():
    service = build_service()
    result = await service.search("삼성", "kr_stock")

    symbols = [c.symbol for c in result.candidates]
    # "삼성전자" (prefix) should appear before "삼성SDS" (prefix) — both are prefix matches
    assert "005930" in symbols
    assert "035420" in symbols
    # prefix matches should come before non-prefix
    assert symbols.index("005930") < len(symbols)


@pytest.mark.asyncio
async def test_search_kr_stock_matches_by_code():
    """Korean stocks are searchable by their 6-digit code, not only by name."""
    service = build_service()
    result = await service.search("005930", "kr_stock")

    symbols = [c.symbol for c in result.candidates]
    assert "005930" in symbols
    assert result.candidates[0].name == "삼성전자"


@pytest.mark.asyncio
async def test_search_kr_stock_partial_code_prefix_match():
    """A partial code prefix matches all codes starting with it."""
    service = build_service()
    result = await service.search("035", "kr_stock")

    symbols = [c.symbol for c in result.candidates]
    # 035720 (카카오) and 035420 (삼성SDS) both start with 035
    assert "035720" in symbols
    assert "035420" in symbols
    # A more specific prefix narrows to a single code.
    narrowed = await service.search("0357", "kr_stock")
    assert [c.symbol for c in narrowed.candidates] == ["035720"]


@pytest.mark.asyncio
async def test_search_kr_stock_still_matches_by_name():
    """Name search keeps working alongside code search for Korean stocks."""
    service = build_service()
    result = await service.search("카카오", "kr_stock")

    symbols = [c.symbol for c in result.candidates]
    assert "035720" in symbols


@pytest.mark.asyncio
async def test_search_kr_stock_dedupes_duplicate_master_entries():
    """A symbol appearing twice in the master must not produce duplicate candidates."""
    dupe_stocks = [
        MasterRecord("005930", "삼성전자", "KOSPI", "stock"),
        MasterRecord("005930", "삼성전자", "KOSPI", "stock"),  # duplicate id
    ]
    service = build_service(krx_stocks=dupe_stocks)
    result = await service.search("삼성", "kr_stock")

    symbols = [c.symbol for c in result.candidates]
    assert symbols.count("005930") == 1


@pytest.mark.asyncio
async def test_search_returns_max_10_candidates():
    many_stocks = [MasterRecord(str(i).zfill(6), f"삼성테스트{i}", "KOSPI", "stock") for i in range(20)]
    service = build_service(krx_stocks=many_stocks)
    result = await service.search("삼성", "kr_stock")

    assert len(result.candidates) <= 10


@pytest.mark.asyncio
async def test_search_us_stock_matches_by_ticker():
    service = build_service()
    result = await service.search("AA", "us_stock")

    symbols = [c.symbol for c in result.candidates]
    # "AAPL" and "AAON" start with "AA" — prefix match
    assert "AAPL" in symbols
    assert "AAON" in symbols
    # "AMZN" does NOT contain "AA" so should not appear
    assert "AMZN" not in symbols


@pytest.mark.asyncio
async def test_search_returns_ok_status_with_timestamp():
    service = build_service()
    result = await service.search("삼성", "kr_stock")

    assert result.status == "ok"
    assert result.as_of is not None


@pytest.mark.asyncio
async def test_get_detail_caches_result():
    service = build_service()
    detail1 = await service.get_detail("005930", "kr_stock")
    detail2 = await service.get_detail("005930", "kr_stock")

    # Yahoo provider should only be called once due to caching
    assert service.yahoo_provider.fetch_detail.call_count == 1  # type: ignore[attr-defined]
    assert detail1.symbol == detail2.symbol


@pytest.mark.asyncio
async def test_get_detail_returns_stale_on_provider_failure():
    yahoo_mock = MagicMock(spec=YahooFinanceProvider)
    first_detail = make_stock_detail()
    yahoo_mock.fetch_detail = AsyncMock(side_effect=[first_detail, ConnectionError("timeout")])
    yahoo_mock.fetch_chart = AsyncMock(return_value=make_chart_response())

    krx_mock = MagicMock(spec=KRXProvider)
    krx_mock.fetch_stock_master = AsyncMock(return_value=make_krx_stocks())
    krx_mock.fetch_etf_master = AsyncMock(return_value=[])

    nasdaq_mock = MagicMock(spec=NasdaqProvider)
    nasdaq_mock.fetch_us_master = AsyncMock(return_value=make_nasdaq_masters())

    service = SearchService(
        krx_provider=krx_mock,
        nasdaq_provider=nasdaq_mock,
        yahoo_provider=yahoo_mock,
        master_ttl_seconds=60,
        quote_ttl_seconds=0,  # TTL 0 forces re-fetch
    )

    # First call succeeds and populates cache
    await service.get_detail("005930", "kr_stock")
    # TTL=0 makes it expire immediately; second call should fail and return stale
    detail = await service.get_detail("005930", "kr_stock")

    assert detail.status == "stale"


@pytest.mark.asyncio
async def test_get_detail_returns_stale_when_provider_returns_unavailable():
    """When yahoo returns status='unavailable', stale cache should be served instead."""
    yahoo_mock = MagicMock(spec=YahooFinanceProvider)
    first_detail = make_stock_detail()
    unavailable_detail = StockDetail(
        symbol="005930",
        name="005930",
        market="KRX",
        asset_type="한국주식",
        exchange="N/A",
        currency="N/A",
        current_price=None,
        open_price=None,
        high_price=None,
        low_price=None,
        prev_close=None,
        change=None,
        change_percent=None,
        volume=None,
        as_of=None,
        source="Yahoo Finance",
        status="unavailable",
        error_message="연결 실패",
    )
    yahoo_mock.fetch_detail = AsyncMock(side_effect=[first_detail, unavailable_detail])
    yahoo_mock.fetch_chart = AsyncMock(return_value=make_chart_response())

    krx_mock = MagicMock(spec=KRXProvider)
    krx_mock.fetch_stock_master = AsyncMock(return_value=make_krx_stocks())
    krx_mock.fetch_etf_master = AsyncMock(return_value=[])

    nasdaq_mock = MagicMock(spec=NasdaqProvider)
    nasdaq_mock.fetch_us_master = AsyncMock(return_value=make_nasdaq_masters())

    service = SearchService(
        krx_provider=krx_mock,
        nasdaq_provider=nasdaq_mock,
        yahoo_provider=yahoo_mock,
        master_ttl_seconds=60,
        quote_ttl_seconds=0,  # TTL 0 forces re-fetch
    )

    # First call succeeds and populates stale cache
    await service.get_detail("005930", "kr_stock")
    # Second call: provider returns unavailable; should return stale cache instead
    detail = await service.get_detail("005930", "kr_stock")

    assert detail.status == "stale"
    assert detail.current_price == 70000.0  # stale data preserved


@pytest.mark.asyncio
async def test_get_chart_returns_stale_when_provider_returns_unavailable():
    """When yahoo chart returns status='unavailable', stale cache should be served instead."""
    yahoo_mock = MagicMock(spec=YahooFinanceProvider)
    first_chart = make_chart_response()
    unavailable_chart = ChartResponse(
        symbol="005930",
        period="1m",
        bars=[],
        source="Yahoo Finance",
        status="unavailable",
        error_message="차트 데이터 없음",
    )
    yahoo_mock.fetch_detail = AsyncMock(return_value=make_stock_detail())
    yahoo_mock.fetch_chart = AsyncMock(side_effect=[first_chart, unavailable_chart])

    krx_mock = MagicMock(spec=KRXProvider)
    krx_mock.fetch_stock_master = AsyncMock(return_value=make_krx_stocks())
    krx_mock.fetch_etf_master = AsyncMock(return_value=[])

    nasdaq_mock = MagicMock(spec=NasdaqProvider)
    nasdaq_mock.fetch_us_master = AsyncMock(return_value=make_nasdaq_masters())

    service = SearchService(
        krx_provider=krx_mock,
        nasdaq_provider=nasdaq_mock,
        yahoo_provider=yahoo_mock,
        master_ttl_seconds=60,
        quote_ttl_seconds=0,  # TTL 0 forces re-fetch
    )

    # First call succeeds and populates stale cache
    await service.get_chart("005930", "1m", "kr_stock")
    # Second call: provider returns unavailable; should return stale cache instead
    chart = await service.get_chart("005930", "1m", "kr_stock")

    assert chart.status == "stale"
    assert len(chart.bars) == 1  # stale bars preserved
