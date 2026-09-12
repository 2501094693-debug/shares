"""东财 F10 完整三张报表（NewFinanceAnalysis）。"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from company.news.financialreport._common import date_str, dedupe_periods, period_label
from core.codes import em_code, normalize_code
from core.http import browser_get

logger = logging.getLogger(__name__)

_F10_BASE = "https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis"
_F10_HEADERS = {"Referer": "https://emweb.securities.eastmoney.com/"}
_DATES_PER_CALL = 5
_SCHEMA_PATH = Path(__file__).with_name("f10_qy_lines.json")
_TABS = {"income": "lrb", "balance": "zcfzb", "cashflow": "xjllb"}

_lines_cache: dict[str, list[dict[str, Any]]] | None = None


def f10_lines(sheet: str = "") -> list[dict[str, Any]] | dict[str, list[dict[str, Any]]]:
    """一般企业完整科目（与东财 F10 利润表/资产负债表/现金流量表一致）。"""
    global _lines_cache
    if _lines_cache is None:
        _lines_cache = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    if sheet:
        return list(_lines_cache.get(sheet) or [])
    return {key: list(val) for key, val in _lines_cache.items()}


def _f10_json(path: str, params: dict[str, Any]) -> dict[str, Any]:
    resp = browser_get(f"{_F10_BASE}/{path}", params=params, headers=_F10_HEADERS, timeout=25)
    resp.raise_for_status()
    payload = resp.json()
    if isinstance(payload, dict):
        return payload
    return {}


def _date_list(tab: str, code: str, *, company_type: str = "4") -> list[str]:
    payload = _f10_json(
        f"{tab}DateAjaxNew",
        {
            "companyType": company_type,
            "reportDateType": "0",
            "code": em_code(code),
        },
    )
    dates: list[str] = []
    for row in payload.get("data") or []:
        if not isinstance(row, dict):
            continue
        day = date_str(row.get("REPORT_DATE"))
        if day:
            dates.append(day)
    return dates


def _annotate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        day = date_str(row.get("REPORT_DATE"))
        item = dict(row)
        item["REPORT_DATE"] = day
        item["PERIOD_LABEL"] = period_label(day, str(item.get("REPORT_DATE_NAME") or ""))
        out.append(item)
    return dedupe_periods(out)


def _fetch_tab(tab: str, code: str, dates: list[str], *, company_type: str = "4") -> list[dict[str, Any]]:
    if not dates:
        return []
    em = em_code(code)
    rows: list[dict[str, Any]] = []
    for i in range(0, len(dates), _DATES_PER_CALL):
        chunk = dates[i : i + _DATES_PER_CALL]
        payload = _f10_json(
            f"{tab}AjaxNew",
            {
                "companyType": company_type,
                "reportDateType": "0",
                "reportType": "1",
                "dates": ",".join(chunk),
                "code": em,
            },
        )
        data = payload.get("data") or []
        if isinstance(data, list):
            rows.extend(row for row in data if isinstance(row, dict))
    return _annotate(rows)


def fetch_f10_statements(code: str, *, page_size: int = 24, company_type: str = "4") -> dict[str, list[dict[str, Any]]]:
    """拉取东财 F10 完整利润表 / 资产负债表 / 现金流量表。"""
    norm = normalize_code(code)
    if not norm:
        return {"income": [], "balance": [], "cashflow": []}

    limit = min(max(int(page_size or 24), 1), 60)
    out = {"income": [], "balance": [], "cashflow": []}

    def _one(sheet: str) -> tuple[str, list[dict[str, Any]]]:
        tab = _TABS[sheet]
        dates = _date_list(tab, norm, company_type=company_type)[:limit]
        return sheet, _fetch_tab(tab, norm, dates, company_type=company_type)

    try:
        with ThreadPoolExecutor(max_workers=3) as pool:
            futs = [pool.submit(_one, sheet) for sheet in _TABS]
            for fut in futs:
                sheet, rows = fut.result()
                out[sheet] = rows
    except Exception as exc:  # noqa: BLE001
        logger.warning("东财 F10 完整报表拉取失败 %s: %s", norm, exc)
    return out
