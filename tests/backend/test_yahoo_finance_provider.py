from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.providers.yahoo_finance import YahooFinanceProvider, _parse_chart, _parse_detail


def make_chart_response(
    symbol: str = "AAPL",
    price: float = 150.0,
    prev_close: float = 149.0,
    volume: int = 1000000,
    timestamps: list[int] | None = None,
    opens: list[float | None] | None = None,
    closes: list[float | None] | None = None,
) -> dict:
    ts = timestamps or [1717545000, 1717631400]
    op = opens or [149.0, 150.0]
    cl = closes or [150.0, 151.0]
    return {
        "chart": {
            "result": [
                {
                    "meta": {
                        "symbol": symbol,
                        "shortName": "Apple Inc.",
                        "exchangeName": "NMS",
                        "currency": "USD",
                        "regularMarketPrice": price,
                        "regularMarketOpen": 148.5,
                        "regularMarketDayHigh": 152.0,
                        "regularMarketDayLow": 147.0,
                        "chartPreviousClose": prev_close,
                        "regularMarketVolume": volume,
                        "regularMarketTime": 1717545000,
                    },
                    "timestamp": ts,
                    "indicators": {
                        "quote": [
                            {
                                "open": op,
                                "high": [h + 1 for h in op],
                                "low": [o - 1 for o in op],
                                "close": cl,
                                "volume": [volume] * len(ts),
                            }
                        ]
                    },
                }
            ]
        }
    }


def test_parse_detail_extracts_price_and_change():
    data = make_chart_response(price=150.0, prev_close=100.0)
    detail = _parse_detail(data, "AAPL", "US", "us_stock")

    assert detail.symbol == "AAPL"
    assert detail.current_price == 150.0
    assert detail.prev_close == 100.0
    assert detail.change == pytest.approx(50.0, abs=0.01)
    assert detail.change_percent == pytest.approx(50.0, abs=0.01)
    assert detail.status == "ok"


def test_parse_detail_handles_null_prev_close_gracefully():
    data = make_chart_response(price=150.0)
    # Remove chartPreviousClose
    data["chart"]["result"][0]["meta"].pop("chartPreviousClose", None)
    data["chart"]["result"][0]["meta"].pop("previousClose", None)
    detail = _parse_detail(data, "AAPL", "US", "us_stock")

    assert detail.change is None
    assert detail.change_percent is None
    assert detail.status == "ok"


def test_parse_detail_returns_unavailable_on_malformed_json():
    bad_data = {"chart": {"result": []}}
    detail = _parse_detail(bad_data, "AAPL", "US", "us_stock")

    assert detail.status == "unavailable"
    assert detail.error_message is not None


def test_parse_chart_extracts_bars_correctly():
    data = make_chart_response(timestamps=[1717545000, 1717631400])
    chart = _parse_chart(data, "AAPL", "1m")

    assert chart.status == "ok"
    assert len(chart.bars) == 2
    assert chart.bars[0].close == 150.0
    assert chart.bars[1].close == 151.0


def test_parse_chart_handles_none_values_in_ohlcv():
    data = make_chart_response()
    data["chart"]["result"][0]["indicators"]["quote"][0]["open"] = [None, 150.0]
    chart = _parse_chart(data, "AAPL", "1m")

    assert chart.bars[0].open is None
    assert chart.bars[1].open == 150.0


def test_parse_chart_returns_unavailable_on_empty_result():
    bad_data = {"chart": {"result": []}}
    chart = _parse_chart(bad_data, "AAPL", "1m")

    assert chart.status == "unavailable"
    assert chart.bars == []


def test_yahoo_provider_normalizes_korean_symbol_to_ks():
    provider = YahooFinanceProvider()
    assert provider.normalize_symbol("005930", "KOSPI", "kr_stock") == "005930.KS"
    assert provider.normalize_symbol("035720", "KOSDAQ", "kr_stock") == "035720.KQ"


def test_yahoo_provider_normalizes_us_symbol_dot_to_dash():
    provider = YahooFinanceProvider()
    assert provider.normalize_symbol("BRK.B", "US", "us_stock") == "BRK-B"
    assert provider.normalize_symbol("AAPL", "US", "us_stock") == "AAPL"


def test_period_params_include_all_required_periods():
    from app.providers.yahoo_finance import _PERIOD_PARAMS

    for period, (range_, interval) in [
        ("3y", ("3y", "1d")),
        ("5y", ("5y", "1d")),
        ("10y", ("10y", "1d")),
        ("ytd", ("ytd", "1d")),
    ]:
        assert period in _PERIOD_PARAMS, f"period '{period}' missing from _PERIOD_PARAMS"
        assert _PERIOD_PARAMS[period] == (range_, interval), (
            f"period '{period}' has wrong mapping: {_PERIOD_PARAMS[period]}"
        )


def test_parse_chart_uses_correct_period_string():
    data = make_chart_response()
    for period in ("3y", "5y", "10y", "ytd"):
        chart = _parse_chart(data, "AAPL", period)
        assert chart.period == period


@pytest.mark.asyncio
async def test_yahoo_provider_fetch_chart_maps_new_periods():
    from app.providers.yahoo_finance import _PERIOD_PARAMS

    provider = YahooFinanceProvider()
    for period in ("3y", "5y", "10y", "ytd"):
        expected_range, expected_interval = _PERIOD_PARAMS[period]
        captured: dict = {}

        async def fake_fetch(yahoo_symbol: str, range_: str, interval: str) -> dict:
            captured["range"] = range_
            captured["interval"] = interval
            return make_chart_response()

        provider._fetch_chart = fake_fetch  # type: ignore[method-assign]
        await provider.fetch_chart("AAPL", period, market="US", asset_type="us_stock")
        assert captured["range"] == expected_range, f"{period}: expected range {expected_range}"
        assert captured["interval"] == expected_interval, f"{period}: expected interval {expected_interval}"


@pytest.mark.asyncio
async def test_yahoo_provider_fetch_detail_returns_unavailable_on_http_error():
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(side_effect=ConnectionError("timeout"))
        mock_client_cls.return_value = mock_client

        provider = YahooFinanceProvider(timeout=5.0)
        detail = await provider.fetch_detail("AAPL", market="US", asset_type="us_stock")

    assert detail.status == "unavailable"
    assert detail.current_price is None
