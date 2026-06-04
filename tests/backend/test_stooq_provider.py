from app.providers.stooq import StooqProvider, parse_stooq_csv


def test_stooq_provider_default_timeout_is_short_for_dashboard_refresh():
    provider = StooqProvider()

    assert provider.timeout_seconds == 4.0


def test_parse_stooq_csv_normalizes_quote_values():
    csv_text = """Symbol,Date,Time,Open,Close,Prev,Name
^SPX,2026-06-03,23:00:00,7605.3,7553.7,7609.8,US LARGECAP
USDKRW,2026-06-04,07:59:04,1529.9,1529.75,1524.53,USD/KRW
"""

    quotes = parse_stooq_csv(csv_text)

    assert quotes["^SPX"].value == 7553.7
    assert quotes["^SPX"].change == -56.1
    assert round(quotes["^SPX"].change_percent, 2) == -0.74
    assert quotes["USDKRW"].source == "Stooq CSV"
    assert quotes["USDKRW"].as_of is not None


def test_parse_stooq_csv_skips_invalid_rows():
    csv_text = """Symbol,Date,Time,Open,Close,Prev,Name
^KQ11,N/D,N/D,N/D,N/D,N/D,^KQ11
BAD,2026-06-03,23:00:00,N/D,not-a-number,1,BAD
"""

    quotes = parse_stooq_csv(csv_text)

    assert quotes == {}
