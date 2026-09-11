"""东财 F10 财务报表：请求与公共工具。"""

from __future__ import annotations

import logging
from typing import Any

from core.codes import normalize_code, ths_code
from core.http import get_json

logger = logging.getLogger(__name__)

_EM_URLS = (
    "https://datacenter.eastmoney.com/securities/api/data/v1/get",
    "https://datacenter-web.eastmoney.com/api/data/v1/get",
)
_EM_HEADERS = {"Referer": "https://emweb.securities.eastmoney.com/"}

MAIN_REPORT = "RPT_F10_FINANCE_MAINFINADATA"
INCOME_REPORT = "RPT_DMSK_FN_INCOME"
BALANCE_REPORT = "RPT_DMSK_FN_BALANCE"
CASH_REPORT = "RPT_DMSK_FN_CASHFLOW"
LICO_REPORT = "RPT_LICO_FN_CPD"

STATEMENT_REPORTS = {
    "main": MAIN_REPORT,
    "income": INCOME_REPORT,
    "balance": BALANCE_REPORT,
    "cashflow": CASH_REPORT,
    "lico": LICO_REPORT,
}


def date_str(value: Any) -> str:
    text = str(value or "").strip()
    return text[:10] if len(text) >= 10 else text


def period_label(report_date: str, name: str = "") -> str:
    if name:
        return str(name).strip()
    day = date_str(report_date)
    if len(day) < 7:
        return day or "—"
    year, month = day[:4], day[5:7]
    mapping = {"03": "一季报", "06": "中报", "09": "三季报", "12": "年报"}
    return f"{year}{mapping.get(month, day)}"


def is_annual(report_date: str) -> bool:
    day = date_str(report_date)
    return len(day) >= 7 and day[5:7] == "12"


def pick(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, "", "-", "--"):
            return row[key]
    return None


def dedupe_periods(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """同一报告期只留一条：优先合并报表（REPORT_TYPE_CODE=001）。"""
    ranked: dict[str, dict[str, Any]] = {}
    for row in rows:
        day = date_str(row.get("REPORT_DATE") or row.get("REPORTDATE"))
        if not day:
            continue
        prev = ranked.get(day)
        if prev is None:
            ranked[day] = row
            continue
        prev_code = str(prev.get("REPORT_TYPE_CODE") or "")
        new_code = str(row.get("REPORT_TYPE_CODE") or "")
        if prev_code != "001" and new_code == "001":
            ranked[day] = row
    return [ranked[k] for k in sorted(ranked, reverse=True)]


def index_by_date(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {date_str(r.get("REPORT_DATE") or r.get("REPORTDATE")): r for r in rows}


def em_get(report_name: str, code: str, *, page_size: int = 20) -> list[dict[str, Any]]:
    """从东财 datacenter 拉取指定报表。"""
    stock = normalize_code(code)
    secu = ths_code(code)
    if not stock:
        return []

    filters = [f'(SECUCODE="{secu}")'] if secu else []
    filters.append(f'(SECURITY_CODE="{stock}")')

    last_exc: Exception | None = None
    for url in _EM_URLS:
        for flt in filters:
            params = {
                "reportName": report_name,
                "columns": "ALL",
                "filter": flt,
                "pageNumber": "1",
                "pageSize": str(page_size),
                "sortTypes": "-1",
                "sortColumns": "REPORT_DATE" if report_name != LICO_REPORT else "REPORTDATE",
                "source": "HSF10" if "securities" in url else "WEB",
                "client": "PC" if "securities" in url else "WEB",
            }
            try:
                payload = get_json(url, params=params, headers=_EM_HEADERS, timeout=20) or {}
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                continue
            result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
            data = result.get("data") or []
            rows = [row for row in data if isinstance(row, dict)]
            if rows:
                return rows
    if last_exc:
        logger.warning("东财 %s 拉取失败 %s: %s", report_name, code, last_exc)
    return []
