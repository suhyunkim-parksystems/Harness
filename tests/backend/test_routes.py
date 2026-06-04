from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.api import routes
from app.main import create_app
from app.models.market import ChartResponse, MarketCollection, MarketItem, MarketSummary


def make_item(item_id: str, category: str) -> MarketItem:
    return MarketItem(
        id=item_id,
        name="S&P 500",
        category=category,
        region="United States",
        symbol="^spx",
        value=100.0,
        change=1.0,
        change_percent=1.0,
        currency="USD",
        as_of=datetime(2026, 6, 4, tzinfo=timezone.utc),
        source="Test",
        status="ok",
        error_message=None,
    )


class FakeMarketService:
    async def get_summary(self):
        return MarketSummary(
            generated_at=datetime(2026, 6, 4, tzinfo=timezone.utc),
            cache_ttl_seconds=30,
            status="ok",
            indices=[make_item("sp500", "us_index")],
            exchange_rates=[make_item("usd_krw", "exchange_rate")],
        )

    async def get_indices(self):
        return MarketCollection(
            generated_at=datetime(2026, 6, 4, tzinfo=timezone.utc),
            cache_ttl_seconds=30,
            status="ok",
            items=[make_item("sp500", "us_index")],
        )

    async def get_exchange_rates(self):
        return MarketCollection(
            generated_at=datetime(2026, 6, 4, tzinfo=timezone.utc),
            cache_ttl_seconds=30,
            status="ok",
            items=[make_item("usd_krw", "exchange_rate")],
        )


class FakeSearchService:
    async def get_chart(self, symbol: str, period: str, category: str) -> ChartResponse:
        return ChartResponse(
            symbol=symbol,
            period=period,
            bars=[],
            source="Test",
            status="ok",
            error_message=None,
        )


def test_chart_api_rejects_invalid_period():
    client = TestClient(create_app())
    response = client.get("/api/stocks/AAPL/chart?category=us_stock&period=invalid")
    assert response.status_code == 422


def test_chart_api_accepts_extended_periods(monkeypatch):
    monkeypatch.setattr(routes, "search_service", FakeSearchService())
    client = TestClient(create_app())

    for period in ("3y", "5y", "10y", "ytd"):
        response = client.get(f"/api/stocks/AAPL/chart?category=us_stock&period={period}")
        assert response.status_code == 200, f"period={period} returned {response.status_code}"
        assert response.json()["period"] == period


def test_chart_api_default_period_is_1m(monkeypatch):
    monkeypatch.setattr(routes, "search_service", FakeSearchService())
    client = TestClient(create_app())

    response = client.get("/api/stocks/AAPL/chart?category=us_stock")
    assert response.status_code == 200
    assert response.json()["period"] == "1m"


def test_health_route_returns_provider_configuration():
    client = TestClient(create_app())

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["providers"]["stooq"] == "configured"


def test_market_routes_return_camel_case_payloads(monkeypatch):
    monkeypatch.setattr(routes, "market_service", FakeMarketService())
    client = TestClient(create_app())

    summary_response = client.get("/api/markets/summary")
    indices_response = client.get("/api/markets/indices")
    rates_response = client.get("/api/markets/exchange-rates")

    assert summary_response.status_code == 200
    assert "generatedAt" in summary_response.json()
    assert "exchangeRates" in summary_response.json()
    assert "changePercent" in summary_response.json()["indices"][0]
    assert indices_response.json()["items"][0]["category"] == "us_index"
    assert rates_response.json()["items"][0]["category"] == "exchange_rate"
