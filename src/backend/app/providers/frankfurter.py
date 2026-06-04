from __future__ import annotations

import asyncio
from datetime import datetime, time, timezone
from typing import Iterable

import httpx

from app.providers.stooq import ProviderQuote
from app.providers.symbols import ExchangeRateSymbol


class FrankfurterProvider:
    def __init__(
        self,
        base_url: str = "https://api.frankfurter.dev/v1/latest",
        timeout_seconds: float = 4.0,
    ) -> None:
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds

    async def fetch_rates(self, pairs: Iterable[ExchangeRateSymbol]) -> dict[str, ProviderQuote]:
        pairs_by_base: dict[str, list[ExchangeRateSymbol]] = {}
        for pair in pairs:
            pairs_by_base.setdefault(pair.base_currency, []).append(pair)

        if not pairs_by_base:
            return {}

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            results = await asyncio.gather(
                *[
                    self._fetch_base_rates(client, base_currency, grouped_pairs)
                    for base_currency, grouped_pairs in pairs_by_base.items()
                ],
                return_exceptions=True,
            )

        quotes: dict[str, ProviderQuote] = {}
        for result in results:
            if isinstance(result, Exception):
                continue
            quotes.update(result)
        return quotes

    async def _fetch_base_rates(
        self,
        client: httpx.AsyncClient,
        base_currency: str,
        pairs: list[ExchangeRateSymbol],
    ) -> dict[str, ProviderQuote]:
        response = await client.get(
            self.base_url,
            params={
                "base": base_currency,
                "symbols": ",".join(pair.quote_currency for pair in pairs),
            },
        )
        response.raise_for_status()
        payload = response.json()
        rates = payload.get("rates") or {}
        as_of = _parse_frankfurter_date(payload.get("date"))

        quotes: dict[str, ProviderQuote] = {}
        for pair in pairs:
            raw_rate = rates.get(pair.quote_currency)
            if raw_rate is None:
                continue
            quotes[pair.symbol.upper()] = ProviderQuote(
                symbol=pair.symbol.upper(),
                value=float(raw_rate),
                change=None,
                change_percent=None,
                as_of=as_of,
                source="Frankfurter",
            )
        return quotes


def _parse_frankfurter_date(date_value: str | None) -> datetime | None:
    if not date_value:
        return None
    try:
        parsed_date = datetime.fromisoformat(date_value).date()
        return datetime.combine(parsed_date, time.min, tzinfo=timezone.utc)
    except ValueError:
        return None
