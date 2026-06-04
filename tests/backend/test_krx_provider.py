from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.providers.krx_provider import KRXProvider, _parse_master_csv


def make_csv_stock():
    return "단축코드,한글 종목명,시장구분\r\n005930,삼성전자,KOSPI\r\n035720,카카오,KOSDAQ\r\n"


def make_csv_etf():
    return "단축코드,한글 종목명,시장구분\r\n069500,KODEX 200,코스피\r\n"


def test_parse_master_csv_stock_parses_market_correctly():
    records = _parse_master_csv(make_csv_stock(), asset_type="stock")

    assert len(records) == 2
    samsung = records[0]
    assert samsung.code == "005930"
    assert samsung.name == "삼성전자"
    assert samsung.market == "KOSPI"
    assert samsung.asset_type == "stock"

    kakao = records[1]
    assert kakao.market == "KOSDAQ"


def test_parse_master_csv_etf_defaults_to_kospi():
    records = _parse_master_csv(make_csv_etf(), asset_type="etf")

    assert len(records) == 1
    etf = records[0]
    assert etf.code == "069500"
    assert etf.name == "KODEX 200"
    assert etf.market == "KOSPI"
    assert etf.asset_type == "etf"


def test_parse_master_csv_skips_rows_with_empty_code_or_name():
    csv_text = "단축코드,한글 종목명,시장구분\r\n,EMPTY CODE,KOSPI\r\n005930,,KOSPI\r\n005930,삼성전자,KOSPI\r\n"
    records = _parse_master_csv(csv_text, asset_type="stock")
    assert len(records) == 1
    assert records[0].code == "005930"


@pytest.mark.asyncio
async def test_krx_provider_returns_empty_on_logout_response():
    """KRX returns LOGOUT text instead of OTP when session expires."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.text = "LOGOUT"

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        provider = KRXProvider(timeout=5.0)
        records = await provider.fetch_stock_master()

    assert records == []


@pytest.mark.asyncio
async def test_krx_provider_returns_empty_on_exception():
    """Provider returns empty list when any exception occurs, not propagating it."""
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=ConnectionError("network error"))
        mock_client_cls.return_value = mock_client

        provider = KRXProvider(timeout=5.0)
        records = await provider.fetch_stock_master()

    assert records == []


def make_csv_stock_with_bom_and_spaces():
    # Leading BOM (﻿) plus padded header cells — the failure mode that
    # otherwise made every column lookup miss and dropped the whole master.
    return (
        "﻿ 단축코드 , 한글 종목명 , 시장구분 \r\n"
        "005930,삼성전자,KOSPI\r\n"
        "035720,카카오,KOSDAQ\r\n"
    )


def test_parse_master_csv_handles_bom_and_whitespace_headers():
    records = _parse_master_csv(make_csv_stock_with_bom_and_spaces(), asset_type="stock")

    assert len(records) == 2
    assert records[0].code == "005930"
    assert records[0].name == "삼성전자"
    assert records[0].market == "KOSPI"
    assert records[1].code == "035720"
    assert records[1].name == "카카오"
    assert records[1].market == "KOSDAQ"


def test_parse_master_csv_returns_empty_on_html_error_page():
    """An HTML error/redirect page must not crash the parser or yield rows."""
    html = "<html><body>session expired</body></html>"
    records = _parse_master_csv(html, asset_type="stock")
    assert records == []


def test_parse_master_csv_returns_empty_on_logout_page():
    """A plain LOGOUT redirect page must yield no records."""
    records = _parse_master_csv("LOGOUT\r\n", asset_type="stock")
    assert records == []


@pytest.mark.asyncio
async def test_krx_provider_decodes_euc_kr_response():
    """CSV content is correctly decoded from EUC-KR bytes."""
    csv_content = "단축코드,한글 종목명,시장구분\r\n005930,삼성전자,KOSPI\r\n"
    otp_response = MagicMock()
    otp_response.raise_for_status = MagicMock()
    otp_response.text = "validotp1234"

    csv_response = MagicMock()
    csv_response.raise_for_status = MagicMock()
    csv_response.content = csv_content.encode("euc-kr")

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=[otp_response, csv_response])
        mock_client_cls.return_value = mock_client

        provider = KRXProvider(timeout=5.0)
        records = await provider.fetch_stock_master()

    assert len(records) == 1
    assert records[0].name == "삼성전자"
