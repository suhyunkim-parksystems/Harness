from __future__ import annotations

import logging

import httpx


logger = logging.getLogger(__name__)

_NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
_OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"

_HEADERS = {"User-Agent": "Mozilla/5.0"}


class NasdaqMasterRecord:
    """A single stock/ETF master record from NASDAQ symbol directory."""

    def __init__(self, symbol: str, name: str, exchange: str, asset_type: str) -> None:
        self.symbol = symbol
        self.name = name
        self.exchange = exchange   # "NASDAQ" | "NYSE" | "AMEX" | "NYSE Arca" | ...
        self.asset_type = asset_type  # "stock" | "etf"


class NasdaqProvider:
    def __init__(self, timeout: float = 10.0) -> None:
        self.timeout = timeout

    async def fetch_us_master(self) -> tuple[list[NasdaqMasterRecord], list[NasdaqMasterRecord]]:
        """Return (stocks, etfs) from NASDAQ + other exchanges."""
        stocks: list[NasdaqMasterRecord] = []
        etfs: list[NasdaqMasterRecord] = []

        try:
            nasdaq_text = await self._download(_NASDAQ_LISTED_URL)
            ns, ne = _parse_nasdaqlisted(nasdaq_text)
            stocks.extend(ns)
            etfs.extend(ne)
        except Exception as exc:
            logger.warning("NASDAQ listed file fetch failed: %s", exc)

        try:
            other_text = await self._download(_OTHER_LISTED_URL)
            os_, oe = _parse_otherlisted(other_text)
            stocks.extend(os_)
            etfs.extend(oe)
        except Exception as exc:
            logger.warning("NASDAQ other listed file fetch failed: %s", exc)

        return stocks, etfs

    async def _download(self, url: str) -> str:
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            response = await client.get(url, headers=_HEADERS)
            response.raise_for_status()
            return response.text


def _parse_nasdaqlisted(text: str) -> tuple[list[NasdaqMasterRecord], list[NasdaqMasterRecord]]:
    """Parse nasdaqlisted.txt (pipe-separated).

    Columns: Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares
    """
    stocks: list[NasdaqMasterRecord] = []
    etfs: list[NasdaqMasterRecord] = []
    lines = text.splitlines()
    for line in lines[1:]:  # skip header
        parts = line.split("|")
        if len(parts) < 7:
            continue
        symbol = parts[0].strip()
        name = parts[1].strip()
        test_issue = parts[3].strip()
        is_etf = parts[6].strip().upper() == "Y"

        if test_issue == "Y" or not symbol or symbol.startswith("File Creation"):
            continue

        record = NasdaqMasterRecord(
            symbol=symbol,
            name=name,
            exchange="NASDAQ",
            asset_type="etf" if is_etf else "stock",
        )
        (etfs if is_etf else stocks).append(record)

    return stocks, etfs


def _parse_otherlisted(text: str) -> tuple[list[NasdaqMasterRecord], list[NasdaqMasterRecord]]:
    """Parse otherlisted.txt (pipe-separated).

    Columns: ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol
    """
    stocks: list[NasdaqMasterRecord] = []
    etfs: list[NasdaqMasterRecord] = []
    lines = text.splitlines()
    for line in lines[1:]:  # skip header
        parts = line.split("|")
        if len(parts) < 7:
            continue
        symbol = parts[0].strip()
        name = parts[1].strip()
        exchange_code = parts[2].strip()
        is_etf = parts[4].strip().upper() == "Y"
        test_issue = parts[6].strip()

        if test_issue == "Y" or not symbol or symbol.startswith("File Creation"):
            continue

        record = NasdaqMasterRecord(
            symbol=symbol,
            name=name,
            exchange=_map_exchange(exchange_code),
            asset_type="etf" if is_etf else "stock",
        )
        (etfs if is_etf else stocks).append(record)

    return stocks, etfs


def _map_exchange(code: str) -> str:
    return {"A": "AMEX", "N": "NYSE", "P": "NYSE Arca", "Z": "BATS", "V": "IEX"}.get(code, code)
