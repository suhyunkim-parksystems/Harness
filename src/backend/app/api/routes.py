from fastapi import APIRouter, HTTPException, Query

from app.config import settings
from app.models.market import AssetCategory, ChartPeriod, ChartResponse, MarketCollection, MarketSummary, SearchResponse, StockDetail
from app.services.market_service import MarketService
from app.services.search_service import SearchService


router = APIRouter()
market_service = MarketService()
search_service = SearchService()


@router.get("/api/health")
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "cacheTtlSeconds": settings.cache_ttl_seconds,
        "providers": {
            "stooq": "configured",
            "frankfurter": "configured",
            "krx": "configured",
            "nasdaq": "configured",
            "yahoo_finance": "configured",
        },
    }


@router.get("/api/markets/summary", response_model=MarketSummary)
async def get_market_summary() -> MarketSummary:
    try:
        return await market_service.get_summary()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="시장 데이터를 가져오지 못했습니다.") from exc


@router.get("/api/markets/indices", response_model=MarketCollection)
async def get_market_indices() -> MarketCollection:
    try:
        return await market_service.get_indices()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="지수 데이터를 가져오지 못했습니다.") from exc


@router.get("/api/markets/exchange-rates", response_model=MarketCollection)
async def get_exchange_rates() -> MarketCollection:
    try:
        return await market_service.get_exchange_rates()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="환율 데이터를 가져오지 못했습니다.") from exc


@router.get("/api/search/autocomplete", response_model=SearchResponse)
async def search_autocomplete(
    q: str = Query(min_length=2, description="검색어 (2자 이상)"),
    category: AssetCategory = Query(description="검색 범주"),
) -> SearchResponse:
    try:
        return await search_service.search(q, category)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="종목 검색에 실패했습니다.") from exc


@router.get("/api/stocks/{symbol}/detail", response_model=StockDetail)
async def get_stock_detail(
    symbol: str,
    category: AssetCategory = Query(description="검색 범주"),
) -> StockDetail:
    try:
        return await search_service.get_detail(symbol, category)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="종목 상세 정보를 가져오지 못했습니다.") from exc


@router.get("/api/stocks/{symbol}/chart", response_model=ChartResponse)
async def get_stock_chart(
    symbol: str,
    category: AssetCategory = Query(description="검색 범주"),
    period: ChartPeriod = Query(default="1m", description="차트 기간"),
) -> ChartResponse:
    try:
        return await search_service.get_chart(symbol, period, category)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="차트 데이터를 가져오지 못했습니다.") from exc
