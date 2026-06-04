from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from app.models.market import ChartBar, ChartResponse, StockDetail


logger = logging.getLogger(__name__)

_CHART_BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

_PERIOD_PARAMS: dict[str, tuple[str, str]] = {
    "1m": ("1mo", "1d"),
    "3m": ("3mo", "1d"),
    "6m": ("6mo", "1d"),
    "1y": ("1y", "1d"),
    "3y": ("3y", "1d"),
    "5y": ("5y", "1d"),
    "10y": ("10y", "1d"),
    "ytd": ("ytd", "1d"),
}

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}


class YahooFinanceProvider:
    def __init__(self, timeout: float = 5.0) -> None:
        self.timeout = timeout

    def normalize_symbol(self, symbol: str, market: str, asset_type: str) -> str:
        """Map internal symbol to Yahoo Finance ticker.

        Korean stocks/ETFs get .KS (KOSPI) or .KQ (KOSDAQ) suffix.
        US symbols have . replaced with - (e.g. BRK.B -> BRK-B).
        """
        if market in ("KOSPI", "KOSDAQ") or asset_type in ("kr_stock", "kr_etf"):
            if symbol.endswith((".KS", ".KQ")):
                return symbol
            suffix = ".KQ" if market == "KOSDAQ" else ".KS"
            return symbol + suffix
        return symbol.replace(".", "-")

    async def fetch_detail(self, symbol: str, market: str = "", asset_type: str = "") -> StockDetail:
        """Fetch current quote detail from Yahoo Finance chart API."""
        yahoo_symbol = self.normalize_symbol(symbol, market, asset_type)
        try:
            data = await self._fetch_chart(yahoo_symbol, range_="1d", interval="1d")
            return _parse_detail(data, symbol, market, asset_type)
        except Exception as exc:
            logger.warning("Yahoo Finance detail fetch failed for %s: %s", symbol, exc)
            return _make_unavailable_detail(symbol, market, asset_type, str(exc))

    async def fetch_chart(
        self, symbol: str, period: str, market: str = "", asset_type: str = ""
    ) -> ChartResponse:
        """Fetch OHLCV daily bars for a given period."""
        yahoo_symbol = self.normalize_symbol(symbol, market, asset_type)
        range_, interval = _PERIOD_PARAMS.get(period, ("1mo", "1d"))
        try:
            data = await self._fetch_chart(yahoo_symbol, range_=range_, interval=interval)
            return _parse_chart(data, symbol, period)
        except Exception as exc:
            logger.warning("Yahoo Finance chart fetch failed for %s: %s", symbol, exc)
            return ChartResponse(
                symbol=symbol,
                period=period,
                bars=[],
                source="Yahoo Finance",
                status="unavailable",
                error_message=str(exc),
            )

    async def _fetch_chart(self, yahoo_symbol: str, range_: str, interval: str) -> dict:
        url = _CHART_BASE_URL.format(symbol=yahoo_symbol)
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            response = await client.get(
                url, params={"range": range_, "interval": interval}, headers=_HEADERS
            )
            response.raise_for_status()
            return response.json()  # type: ignore[no-any-return]


def _parse_detail(data: dict, symbol: str, market: str, asset_type: str) -> StockDetail:
    try:
        result = data["chart"]["result"][0]
        meta = result.get("meta", {})

        name = meta.get("shortName") or meta.get("longName") or symbol
        exchange = meta.get("exchangeName") or meta.get("fullExchangeName") or ""
        currency = meta.get("currency") or "USD"

        current_price = meta.get("regularMarketPrice")
        prev_close = meta.get("chartPreviousClose") or meta.get("previousClose")
        open_price = meta.get("regularMarketOpen")
        high_price = meta.get("regularMarketDayHigh")
        low_price = meta.get("regularMarketDayLow")
        volume_raw = meta.get("regularMarketVolume")
        volume = int(volume_raw) if volume_raw is not None else None

        change: float | None = None
        change_percent: float | None = None
        if current_price is not None and prev_close is not None and prev_close != 0:
            change = round(current_price - prev_close, 4)
            change_percent = round((change / prev_close) * 100, 4)

        as_of: datetime | None = None
        ts = meta.get("regularMarketTime")
        if ts:
            try:
                as_of = datetime.fromtimestamp(int(ts), tz=timezone.utc)
            except Exception:
                pass

        return StockDetail(
            symbol=symbol,
            name=name,
            market=_friendly_market(market, asset_type),
            asset_type=_asset_type_label(asset_type),
            exchange=exchange,
            currency=currency,
            current_price=current_price,
            open_price=open_price,
            high_price=high_price,
            low_price=low_price,
            prev_close=prev_close,
            change=change,
            change_percent=change_percent,
            volume=volume,
            as_of=as_of,
            source="Yahoo Finance",
            status="ok",
            error_message=None,
        )
    except (KeyError, IndexError, TypeError) as exc:
        logger.warning("Yahoo Finance detail parse error for %s: %s", symbol, exc)
        return _make_unavailable_detail(symbol, market, asset_type, "일부 시세 정보 파싱 불가")


def _parse_chart(data: dict, symbol: str, period: str) -> ChartResponse:
    try:
        result = data["chart"]["result"][0]
        timestamps = result.get("timestamp") or []
        indicators = result.get("indicators", {})
        quote_list = indicators.get("quote", [{}])
        quote = quote_list[0] if quote_list else {}

        opens = quote.get("open") or []
        highs = quote.get("high") or []
        lows = quote.get("low") or []
        closes = quote.get("close") or []
        volumes = quote.get("volume") or []

        bars: list[ChartBar] = []
        for i, ts in enumerate(timestamps):
            try:
                dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
                timestamp_str = dt.strftime("%Y-%m-%d")
            except Exception:
                continue

            o = opens[i] if i < len(opens) else None
            h = highs[i] if i < len(highs) else None
            lo = lows[i] if i < len(lows) else None
            c = closes[i] if i < len(closes) else None
            v_raw = volumes[i] if i < len(volumes) else None
            v = int(v_raw) if v_raw is not None else None

            bars.append(ChartBar(timestamp=timestamp_str, open=o, high=h, low=lo, close=c, volume=v))

        return ChartResponse(
            symbol=symbol,
            period=period,
            bars=bars,
            source="Yahoo Finance",
            status="ok" if bars else "unavailable",
            error_message=None if bars else "차트 데이터가 없습니다.",
        )
    except (KeyError, IndexError, TypeError) as exc:
        logger.warning("Yahoo Finance chart parse error for %s: %s", symbol, exc)
        return ChartResponse(
            symbol=symbol,
            period=period,
            bars=[],
            source="Yahoo Finance",
            status="unavailable",
            error_message="차트 데이터 파싱 중 오류가 발생했습니다.",
        )


def _make_unavailable_detail(symbol: str, market: str, asset_type: str, msg: str) -> StockDetail:
    return StockDetail(
        symbol=symbol,
        name=symbol,
        market=_friendly_market(market, asset_type),
        asset_type=_asset_type_label(asset_type),
        exchange="N/A",
        currency="N/A",
        current_price=None,
        open_price=None,
        high_price=None,
        low_price=None,
        prev_close=None,
        change=None,
        change_percent=None,
        volume=None,
        as_of=None,
        source="Yahoo Finance",
        status="unavailable",
        error_message=msg,
    )


def _friendly_market(market: str, asset_type: str) -> str:
    if market in ("KOSPI", "KOSDAQ"):
        return market
    if asset_type in ("kr_stock", "kr_etf"):
        return "KRX"
    return "US"


def _asset_type_label(asset_type: str) -> str:
    return {
        "kr_stock": "한국주식",
        "kr_etf": "한국ETF",
        "us_stock": "미국주식",
        "us_etf": "미국ETF",
    }.get(asset_type, asset_type)
