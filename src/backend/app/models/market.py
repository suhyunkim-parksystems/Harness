from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


MarketStatus = Literal["ok", "stale", "unavailable"]
SummaryStatus = Literal["ok", "partial", "unavailable"]
AssetCategory = Literal["kr_stock", "kr_etf", "us_stock", "us_etf"]
ChartPeriod = Literal["1m", "3m", "6m", "1y", "3y", "5y", "10y", "ytd"]


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class MarketItem(ApiModel):
    id: str
    name: str
    category: str
    region: str
    symbol: str
    value: float | None
    change: float | None
    change_percent: float | None = Field(default=None, alias="changePercent")
    currency: str
    as_of: datetime | None = Field(default=None, alias="asOf")
    source: str
    status: MarketStatus
    error_message: str | None = Field(default=None, alias="errorMessage")


class MarketSummary(ApiModel):
    generated_at: datetime = Field(alias="generatedAt")
    cache_ttl_seconds: int = Field(alias="cacheTtlSeconds")
    status: SummaryStatus
    indices: list[MarketItem]
    exchange_rates: list[MarketItem] = Field(alias="exchangeRates")


class MarketCollection(ApiModel):
    generated_at: datetime = Field(alias="generatedAt")
    cache_ttl_seconds: int = Field(alias="cacheTtlSeconds")
    status: SummaryStatus
    items: list[MarketItem]


class SearchCandidate(ApiModel):
    id: str
    market: str
    asset_type: str = Field(alias="assetType")
    symbol: str
    name: str
    exchange: str
    currency: str
    match_text: str = Field(alias="matchText")
    source: str
    status: MarketStatus


class SearchResponse(ApiModel):
    candidates: list[SearchCandidate]
    status: str
    as_of: datetime | None = Field(default=None, alias="asOf")


class StockDetail(ApiModel):
    symbol: str
    name: str
    market: str
    asset_type: str = Field(alias="assetType")
    exchange: str
    currency: str
    current_price: float | None = Field(default=None, alias="currentPrice")
    open_price: float | None = Field(default=None, alias="openPrice")
    high_price: float | None = Field(default=None, alias="highPrice")
    low_price: float | None = Field(default=None, alias="lowPrice")
    prev_close: float | None = Field(default=None, alias="prevClose")
    change: float | None = None
    change_percent: float | None = Field(default=None, alias="changePercent")
    volume: int | None = None
    as_of: datetime | None = Field(default=None, alias="asOf")
    source: str
    status: MarketStatus
    error_message: str | None = Field(default=None, alias="errorMessage")


class ChartBar(ApiModel):
    timestamp: str
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: int | None = None


class ChartResponse(ApiModel):
    symbol: str
    period: str
    bars: list[ChartBar]
    source: str
    status: MarketStatus
    error_message: str | None = Field(default=None, alias="errorMessage")
