from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from io import StringIO
from typing import Iterable

import httpx


@dataclass(frozen=True)
class ProviderQuote:
    symbol: str
    value: float
    change: float | None
    change_percent: float | None
    as_of: datetime | None
    source: str


class StooqProvider:
    def __init__(
        self,
        base_url: str = "https://stooq.com/q/l/",
        timeout_seconds: float = 4.0,
    ) -> None:
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds

    async def fetch_quotes(self, symbols: Iterable[str]) -> dict[str, ProviderQuote]:
        normalized_symbols = [symbol.lower() for symbol in symbols]
        if not normalized_symbols:
            return {}

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(
                self.base_url,
                params={
                    "s": " ".join(normalized_symbols),
                    "f": "sd2t2ocpn",
                    "h": "",
                    "e": "csv",
                },
            )
            response.raise_for_status()

        return parse_stooq_csv(response.text)


def parse_stooq_csv(csv_text: str) -> dict[str, ProviderQuote]:
    reader = csv.DictReader(StringIO(csv_text.strip()))
    quotes: dict[str, ProviderQuote] = {}

    for row in reader:
        symbol = (row.get("Symbol") or "").upper()
        close_value = _parse_number(row.get("Close"))
        previous_value = _parse_number(row.get("Prev"))

        if not symbol or close_value is None:
            continue

        change = None
        change_percent = None
        if previous_value and previous_value != 0:
            change = round(close_value - previous_value, 6)
            change_percent = round((change / previous_value) * 100, 6)

        quotes[symbol] = ProviderQuote(
            symbol=symbol,
            value=close_value,
            change=change,
            change_percent=change_percent,
            as_of=_parse_datetime(row.get("Date"), row.get("Time")),
            source="Stooq CSV",
        )

    return quotes


def _parse_number(value: str | None) -> float | None:
    if value is None:
        return None
    normalized = value.strip().replace(",", "")
    if not normalized or normalized.upper() == "N/D":
        return None
    try:
        return float(normalized)
    except ValueError:
        return None


def _parse_datetime(date_value: str | None, time_value: str | None) -> datetime | None:
    if not date_value or not time_value:
        return None
    if date_value.upper() == "N/D" or time_value.upper() == "N/D":
        return None
    try:
        return datetime.fromisoformat(f"{date_value}T{time_value}").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
