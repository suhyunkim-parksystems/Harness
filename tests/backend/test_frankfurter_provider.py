from app.providers.frankfurter import FrankfurterProvider
from app.providers.symbols import EXCHANGE_RATE_SYMBOLS
import pytest


pytestmark = pytest.mark.asyncio


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        self.requests = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, url, params):
        self.requests.append((url, params))
        return FakeResponse(
            {
                "amount": 1.0,
                "base": params["base"],
                "date": "2026-06-03",
                "rates": {symbol: 100.0 for symbol in params["symbols"].split(",")},
            }
        )


async def test_frankfurter_provider_default_timeout_is_short_for_dashboard_refresh():
    provider = FrankfurterProvider()

    assert provider.timeout_seconds == 4.0


async def test_frankfurter_provider_groups_pairs_by_base(monkeypatch):
    monkeypatch.setattr("app.providers.frankfurter.httpx.AsyncClient", FakeAsyncClient)
    provider = FrankfurterProvider()

    quotes = await provider.fetch_rates(EXCHANGE_RATE_SYMBOLS)

    assert quotes["USDKRW"].value == 100.0
    assert quotes["EURUSD"].source == "Frankfurter"
    assert quotes["GBPUSD"].change is None
    assert quotes["USDCNY"].as_of is not None


async def test_frankfurter_provider_returns_empty_on_request_failure(monkeypatch):
    class FailingClient(FakeAsyncClient):
        async def get(self, url, params):
            raise TimeoutError("timeout")

    monkeypatch.setattr("app.providers.frankfurter.httpx.AsyncClient", FailingClient)
    provider = FrankfurterProvider()

    quotes = await provider.fetch_rates(EXCHANGE_RATE_SYMBOLS)

    assert quotes == {}
