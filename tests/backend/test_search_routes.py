from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api import routes
from app.main import create_app
from app.models.market import ChartBar, ChartResponse, SearchCandidate, SearchResponse, StockDetail


def make_candidate(symbol: str, name: str) -> SearchCandidate:
    return SearchCandidate(
        id=f"us:{symbol}",
        market="US",
        asset_type="us_stock",
        symbol=symbol,
        name=name,
        exchange="NASDAQ",
        currency="USD",
        match_text=f"{symbol} {name}",
        source="NASDAQ",
        status="ok",
    )


def make_detail(symbol: str = "AAPL") -> StockDetail:
    return StockDetail(
        symbol=symbol,
        name="Apple Inc.",
        market="US",
        asset_type="미국주식",
        exchange="NASDAQ",
        currency="USD",
        current_price=150.0,
        open_price=148.0,
        high_price=152.0,
        low_price=147.0,
        prev_close=149.0,
        change=1.0,
        change_percent=0.67,
        volume=65000000,
        as_of=datetime(2026, 6, 4, tzinfo=timezone.utc),
        source="Yahoo Finance",
        status="ok",
        error_message=None,
    )


def make_chart(symbol: str = "AAPL") -> ChartResponse:
    return ChartResponse(
        symbol=symbol,
        period="1m",
        bars=[
            ChartBar(timestamp="2026-06-04", open=148.0, high=152.0, low=147.0, close=150.0, volume=65000000)
        ],
        source="Yahoo Finance",
        status="ok",
        error_message=None,
    )


class FakeSearchService:
    async def search(self, query: str, category: str) -> SearchResponse:
        return SearchResponse(
            candidates=[make_candidate("AAPL", "Apple Inc.")],
            status="ok",
            as_of=datetime(2026, 6, 4, tzinfo=timezone.utc),
        )

    async def get_detail(self, symbol: str, category: str) -> StockDetail:
        return make_detail(symbol)

    async def get_chart(self, symbol: str, period: str, category: str) -> ChartResponse:
        return make_chart(symbol)


def test_autocomplete_returns_candidates(monkeypatch):
    monkeypatch.setattr(routes, "search_service", FakeSearchService())
    client = TestClient(create_app())

    response = client.get("/api/search/autocomplete", params={"q": "AA", "category": "us_stock"})

    assert response.status_code == 200
    body = response.json()
    assert "candidates" in body
    assert body["candidates"][0]["symbol"] == "AAPL"


def test_autocomplete_requires_minimum_2_chars(monkeypatch):
    monkeypatch.setattr(routes, "search_service", FakeSearchService())
    client = TestClient(create_app())

    response = client.get("/api/search/autocomplete", params={"q": "A", "category": "us_stock"})

    assert response.status_code == 422  # FastAPI validation error


def test_autocomplete_rejects_invalid_category(monkeypatch):
    monkeypatch.setattr(routes, "search_service", FakeSearchService())
    client = TestClient(create_app())

    response = client.get("/api/search/autocomplete", params={"q": "AAPL", "category": "crypto"})

    assert response.status_code == 422


def test_stock_detail_returns_camel_case_json(monkeypatch):
    monkeypatch.setattr(routes, "search_service", FakeSearchService())
    client = TestClient(create_app())

    response = client.get("/api/stocks/AAPL/detail", params={"category": "us_stock"})

    assert response.status_code == 200
    body = response.json()
    assert "currentPrice" in body
    assert "changePercent" in body
    assert "asOf" in body
    assert body["symbol"] == "AAPL"


def test_stock_chart_returns_bars(monkeypatch):
    monkeypatch.setattr(routes, "search_service", FakeSearchService())
    client = TestClient(create_app())

    response = client.get("/api/stocks/AAPL/chart", params={"category": "us_stock", "period": "1m"})

    assert response.status_code == 200
    body = response.json()
    assert "bars" in body
    assert len(body["bars"]) == 1
    assert body["bars"][0]["close"] == 150.0


def test_stock_chart_defaults_to_1m_period(monkeypatch):
    monkeypatch.setattr(routes, "search_service", FakeSearchService())
    client = TestClient(create_app())

    response = client.get("/api/stocks/AAPL/chart", params={"category": "us_stock"})

    assert response.status_code == 200


def test_autocomplete_returns_camel_case_response(monkeypatch):
    monkeypatch.setattr(routes, "search_service", FakeSearchService())
    client = TestClient(create_app())

    response = client.get("/api/search/autocomplete", params={"q": "AA", "category": "us_stock"})

    body = response.json()
    candidate = body["candidates"][0]
    assert "assetType" in candidate
    assert "matchText" in candidate
