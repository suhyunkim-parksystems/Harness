from __future__ import annotations

import csv
import io
import logging
from datetime import date

import httpx


logger = logging.getLogger(__name__)

_GENERATE_OTP_URL = "http://data.krx.co.kr/comm/fileDn/GenerateOTP/generate.cmd"
_DOWNLOAD_URL = "http://data.krx.co.kr/comm/fileDn/download_csv/download.cmd"

_STOCK_OTP_PARAMS: dict[str, str] = {
    "locale": "ko_KR",
    "share": "1",
    "money": "1",
    "csvxls_isNo": "false",
    "name": "fileDown",
    "url": "dbms/MDC/STAT/standard/MDCSTAT01901",
}

_ETF_OTP_PARAMS: dict[str, str] = {
    "locale": "ko_KR",
    "csvxls_isNo": "false",
    "name": "fileDown",
    "url": "dbms/MDC/STAT/standard/MDCSTAT04001",
}

_HEADERS = {
    "Referer": "http://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd",
    "User-Agent": "Mozilla/5.0",
}

# Invisible marks that can corrupt KRX CSV headers/values.
_BOM = "﻿"
_ZERO_WIDTH_SPACE = "​"


class MasterRecord:
    """A single stock/ETF master record from KRX."""

    def __init__(self, code: str, name: str, market: str, asset_type: str) -> None:
        self.code = code
        self.name = name
        self.market = market       # "KOSPI" | "KOSDAQ"
        self.asset_type = asset_type  # "stock" | "etf"


class KRXProvider:
    def __init__(self, timeout: float = 10.0) -> None:
        self.timeout = timeout

    async def fetch_stock_master(self) -> list[MasterRecord]:
        """Fetch KOSPI and KOSDAQ stock master from KRX Data Marketplace."""
        try:
            today = date.today().strftime("%Y%m%d")
            params = {**_STOCK_OTP_PARAMS, "trdDd": today}
            return await self._fetch_master(params, asset_type="stock")
        except Exception as exc:
            logger.warning("KRX stock master fetch failed: %s", exc)
            return []

    async def fetch_etf_master(self) -> list[MasterRecord]:
        """Fetch KRX ETF master from KRX Data Marketplace."""
        try:
            return await self._fetch_master(_ETF_OTP_PARAMS, asset_type="etf")
        except Exception as exc:
            logger.warning("KRX ETF master fetch failed: %s", exc)
            return []

    async def _fetch_master(self, otp_params: dict[str, str], asset_type: str) -> list[MasterRecord]:
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            otp_response = await client.post(_GENERATE_OTP_URL, data=otp_params, headers=_HEADERS)
            otp_response.raise_for_status()
            otp = otp_response.text.strip()

            if not otp or "<" in otp or "LOGOUT" in otp.upper():
                raise ValueError(f"Invalid OTP response from KRX: {otp[:80]!r}")

            csv_response = await client.post(_DOWNLOAD_URL, data={"code": otp}, headers=_HEADERS)
            csv_response.raise_for_status()

            content = csv_response.content
            try:
                text = content.decode("euc-kr")
            except UnicodeDecodeError:
                text = content.decode("utf-8", errors="replace")

            if "LOGOUT" in text.upper() or text.strip().startswith("<"):
                raise ValueError("KRX returned login/redirect page instead of CSV")

            return _parse_master_csv(text, asset_type)


def _parse_master_csv(text: str, asset_type: str) -> list[MasterRecord]:
    records: list[MasterRecord] = []

    # Strip a leading BOM so the first header cell is not corrupted (e.g. a BOM
    # prefixing "단축코드"), which would otherwise make every column lookup miss
    # and silently drop the whole master list.
    text = text.lstrip(_BOM)
    stripped = text.strip()

    # Defensive guard: KRX sometimes returns an HTML error/redirect or a plain
    # LOGOUT page instead of CSV. Return empty instead of parsing garbage rows.
    if not stripped or stripped.startswith("<") or stripped.upper().startswith("LOGOUT"):
        logger.warning("KRX master CSV looks like an error/redirect page; skipping parse")
        return records

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return records

    for raw_row in reader:
        row = _normalize_row(raw_row)
        # Try multiple column name variants for robustness
        code = row.get("단축코드") or row.get("종목코드") or row.get("표준코드") or ""
        name = row.get("한글 종목명") or row.get("한글종목명") or row.get("종목명") or ""
        market_raw = row.get("시장구분") or row.get("소속부") or ""

        if not code or not name:
            continue

        if "코스닥" in market_raw or "KOSDAQ" in market_raw.upper():
            market = "KOSDAQ"
        else:
            market = "KOSPI"

        records.append(MasterRecord(code=code, name=name, market=market, asset_type=asset_type))

    return records


def _normalize_row(raw_row: dict) -> dict[str, str]:
    """Trim BOM/zero-width marks and surrounding whitespace from keys and values.

    KRX headers occasionally arrive with a BOM, zero-width spaces, or padding
    whitespace; normalizing both keys and values keeps column lookups reliable.
    """
    normalized: dict[str, str] = {}
    for key, value in raw_row.items():
        if key is None:
            continue
        clean_key = key.replace(_BOM, "").replace(_ZERO_WIDTH_SPACE, "").strip()
        normalized[clean_key] = (value or "").strip()
    return normalized
