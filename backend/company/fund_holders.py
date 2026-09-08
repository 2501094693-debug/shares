"""个股基金持股：东财数据中心 ``RPT_MAINDATA_MAIN_POSITIONDETAILS``。"""

from __future__ import annotations

import logging
import time
from typing import Any

from core.cache import TtlCache
from core.codes import normalize_code
from core.fmt import fmt_yi_wan, to_float
from core.http import get_json

logger = logging.getLogger(__name__)

_API = "https://datacenter-web.eastmoney.com/api/data/v1/get"
_REPORT = "RPT_MAINDATA_MAIN_POSITIONDETAILS"
_HEADERS = {"Referer": "https://data.eastmoney.com/"}
_PAGE_SIZE = 500
_MAX_PAGES = 20
_CACHE_TTL = 6 * 60 * 60

_cache = TtlCache(_CACHE_TTL)


def _report_date(value: Any) -> str:
    text = str(value or "").strip()
    return text[:10] if len(text) >= 10 else text


def _dc_page(
    code: str,
    *,
    report_date: str | None = None,
    page: int = 1,
    page_size: int = _PAGE_SIZE,
    sort_column: str = "NETASSET_RATIO",
) -> dict[str, Any]:
    filt = f'(SECURITY_CODE="{code}")'
    if report_date:
        filt += f"(REPORT_DATE='{report_date}')"
    payload = get_json(
        _API,
        params={
            "sortColumns": sort_column,
            "sortTypes": "-1",
            "pageSize": str(page_size),
            "pageNumber": str(page),
            "reportName": _REPORT,
            "columns": "ALL",
            "filter": filt,
            "source": "WEB",
            "client": "WEB",
        },
        headers=_HEADERS,
        timeout=(6, 25),
        retries=1,
    )
    if not isinstance(payload, dict) or not payload.get("success"):
        message = str(payload.get("message") or "东财基金持股接口失败")
        raise RuntimeError(message)
    result = payload.get("result")
    if not isinstance(result, dict):
        raise RuntimeError("东财基金持股返回格式异常")
    return result


def _latest_report_date(code: str) -> str:
    result = _dc_page(code, page=1, page_size=1, sort_column="REPORT_DATE")
    rows = result.get("data") or []
    if not rows:
        raise RuntimeError("暂无基金持股报告期")
    return _report_date(rows[0].get("REPORT_DATE"))


def _fmt_ratio(value: Any) -> str:
    number = to_float(value)
    if number is None:
        return ""
    if abs(number) < 0.01:
        return f"{number:.4f}%"
    return f"{number:.2f}%"


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    code = str(row.get("HOLDER_CODE") or "").strip()
    name = str(row.get("HOLDER_NAME") or "").strip()
    net_ratio = to_float(row.get("NETASSET_RATIO"))
    free_ratio = to_float(row.get("FREE_SHARES_RATIO"))
    total_ratio = to_float(row.get("TOTAL_SHARES_RATIO"))
    market_cap = to_float(row.get("HOLD_MARKET_CAP"))
    shares = to_float(row.get("TOTAL_SHARES"))
    return {
        "code": code,
        "name": name,
        "org_type": str(row.get("ORG_TYPE") or "").strip(),
        "weight": _fmt_ratio(net_ratio),
        "weight_raw": net_ratio,
        "free_float_ratio": _fmt_ratio(free_ratio),
        "free_float_ratio_raw": free_ratio,
        "total_share_ratio": _fmt_ratio(total_ratio),
        "total_share_ratio_raw": total_ratio,
        "market_value": fmt_yi_wan(market_cap),
        "market_value_raw": market_cap,
        "shares": shares,
        "report_date": _report_date(row.get("REPORT_DATE")),
    }


def fetch_fund_holders(
    code: str,
    *,
    report_date: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """拉取持有该股票的全部基金及持仓比例（按占净值比降序）。"""
    code = normalize_code(code)
    if not code:
        raise ValueError("缺少股票代码")

    cache_key = f"{code}:{report_date or 'latest'}"
    if not force:
        cached = _cache.get(cache_key)
        if cached:
            return cached

    date = (report_date or "").strip() or _latest_report_date(code)
    items: list[dict[str, Any]] = []
    pages = 1
    for page in range(1, _MAX_PAGES + 1):
        result = _dc_page(code, report_date=date, page=page)
        rows = result.get("data") or []
        if not isinstance(rows, list):
            break
        for row in rows:
            if isinstance(row, dict):
                items.append(_normalize_row(row))
        pages = int(result.get("pages") or 1)
        if page >= pages:
            break

    if not items:
        raise RuntimeError("暂无基金持股数据")

    payload = {
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "code": code,
        "report_date": date,
        "count": len(items),
        "items": items,
        "source": "eastmoney",
    }
    _cache.put(cache_key, payload)
    return payload
