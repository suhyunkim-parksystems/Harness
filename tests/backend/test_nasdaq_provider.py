from unittest.mock import AsyncMock, patch

import pytest

from app.providers.nasdaq_provider import NasdaqProvider, _parse_nasdaqlisted, _parse_otherlisted


NASDAQ_LISTED_SAMPLE = (
    "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares\n"
    "AAPL|Apple Inc.|Q|N|N|100|N|N\n"
    "NVDA|NVIDIA Corporation|Q|N|N|100|N|N\n"
    "SQQQ|ProShares UltraPro Short QQQ|Q|N|N|100|Y|N\n"
    "TEST|Test Symbol|Q|Y|N|100|N|N\n"  # Test Issue - should be excluded
    "File Creation Time: 06/04/2026|||||||||"  # Footer row - excluded
)

OTHER_LISTED_SAMPLE = (
    "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol\n"
    "BRK/A|Berkshire Hathaway|N|BRK/A|N|1|N|BRKNA\n"
    "SPY|SPDR S&P 500 ETF Trust|P|SPY|Y|100|N|SPY\n"
    "ZTEST|Zeta Test|N|ZTEST|N|100|Y|ZTEST\n"  # Test Issue - excluded
)


def test_parse_nasdaqlisted_separates_stocks_from_etfs():
    stocks, etfs = _parse_nasdaqlisted(NASDAQ_LISTED_SAMPLE)

    stock_symbols = [s.symbol for s in stocks]
    etf_symbols = [e.symbol for e in etfs]

    assert "AAPL" in stock_symbols
    assert "NVDA" in stock_symbols
    assert "SQQQ" in etf_symbols
    assert "TEST" not in stock_symbols  # test issue excluded
    assert not any(s.symbol.startswith("File Creation") for s in stocks + etfs)


def test_parse_nasdaqlisted_sets_exchange_to_nasdaq():
    stocks, _ = _parse_nasdaqlisted(NASDAQ_LISTED_SAMPLE)
    assert all(s.exchange == "NASDAQ" for s in stocks)


def test_parse_otherlisted_maps_exchange_codes():
    stocks, etfs = _parse_otherlisted(OTHER_LISTED_SAMPLE)

    stock_symbols = [s.symbol for s in stocks]
    etf_symbols = [e.symbol for e in etfs]

    brk_record = next(s for s in stocks if s.symbol == "BRK/A")
    assert brk_record.exchange == "NYSE"

    spy_record = next(e for e in etfs if e.symbol == "SPY")
    assert spy_record.exchange == "NYSE Arca"

    assert "ZTEST" not in stock_symbols  # test issue excluded


@pytest.mark.asyncio
async def test_nasdaq_provider_returns_empty_on_download_failure():
    """Each file failure is isolated; total result may be partial."""
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(side_effect=ConnectionError("timeout"))
        mock_client_cls.return_value = mock_client

        provider = NasdaqProvider(timeout=5.0)
        stocks, etfs = await provider.fetch_us_master()

    assert stocks == []
    assert etfs == []


@pytest.mark.asyncio
async def test_nasdaq_provider_combines_both_files():
    from unittest.mock import MagicMock

    nasdaq_resp = MagicMock()
    nasdaq_resp.raise_for_status = MagicMock()
    nasdaq_resp.text = NASDAQ_LISTED_SAMPLE

    other_resp = MagicMock()
    other_resp.raise_for_status = MagicMock()
    other_resp.text = OTHER_LISTED_SAMPLE

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(side_effect=[nasdaq_resp, other_resp])
        mock_client_cls.return_value = mock_client

        provider = NasdaqProvider(timeout=5.0)
        stocks, etfs = await provider.fetch_us_master()

    stock_symbols = [s.symbol for s in stocks]
    etf_symbols = [e.symbol for e in etfs]

    assert "AAPL" in stock_symbols
    assert "BRK/A" in stock_symbols
    assert "SQQQ" in etf_symbols
    assert "SPY" in etf_symbols
