from dataclasses import dataclass


@dataclass(frozen=True)
class MarketSymbol:
    id: str
    name: str
    category: str
    region: str
    symbol: str
    currency: str


@dataclass(frozen=True)
class ExchangeRateSymbol(MarketSymbol):
    base_currency: str
    quote_currency: str


INDEX_SYMBOLS: tuple[MarketSymbol, ...] = (
    MarketSymbol("sp500", "S&P 500", "us_index", "United States", "^spx", "USD"),
    MarketSymbol("nasdaq100", "Nasdaq 100", "us_index", "United States", "^ndx", "USD"),
    MarketSymbol("dow_jones", "Dow Jones Industrial Average", "us_index", "United States", "^dji", "USD"),
    MarketSymbol("kospi", "KOSPI", "korea_index", "South Korea", "^kospi", "KRW"),
    MarketSymbol("nikkei225", "Nikkei 225", "global_index", "Japan", "^nkx", "JPY"),
    MarketSymbol("dax", "DAX", "global_index", "Germany", "^dax", "EUR"),
    MarketSymbol("ftse100", "FTSE 100", "global_index", "United Kingdom", "^ukx", "GBP"),
    MarketSymbol("shanghai_composite", "Shanghai Composite", "global_index", "China", "^shc", "CNY"),
    MarketSymbol("hang_seng", "Hang Seng", "global_index", "Hong Kong", "^hsi", "HKD"),
)


EXCHANGE_RATE_SYMBOLS: tuple[ExchangeRateSymbol, ...] = (
    ExchangeRateSymbol("usd_krw", "USD/KRW", "exchange_rate", "FX", "usdkrw", "KRW", "USD", "KRW"),
    ExchangeRateSymbol("usd_jpy", "USD/JPY", "exchange_rate", "FX", "usdjpy", "JPY", "USD", "JPY"),
    ExchangeRateSymbol("eur_usd", "EUR/USD", "exchange_rate", "FX", "eurusd", "USD", "EUR", "USD"),
    ExchangeRateSymbol("usd_cny", "USD/CNY", "exchange_rate", "FX", "usdcny", "CNY", "USD", "CNY"),
    ExchangeRateSymbol("gbp_usd", "GBP/USD", "exchange_rate", "FX", "gbpusd", "USD", "GBP", "USD"),
)
