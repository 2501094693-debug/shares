"""个股股东户数走势：东财 ``RPT_HOLDERNUM_DET``。

按报告期给出股东户数、环比变动、户均持股等，供前端画走势图。

    python -m company.statistics.holdings 600519 --holder-num
    python -m company.statistics.holdings 600519 --holder-num --limit 8 --json
"""

from __future__ import annotations

import logging
import time
from typing import Any

from core.cache import TtlCache
from core.codes import normalize_code
from core.fmt import fmt_pct, fmt_shares, fmt_yi_wan, to_float
from core.http import get_json

logger = logging.getLogger(__name__)

_API = "https://datacenter-web.eastmoney.com/api/data/v1/get"
_REPORT = "RPT_HOLDERNUM_DET"
_HEADERS = {"Referer": "https://data.eastmoney.com/"}
_CACHE_TTL = 6 * 60 * 60
_PAGE_SIZE = 200
_MAX_PAGES = 4
_DEFAULT_LIMIT = 80

_cache = TtlCache(_CACHE_TTL)


def _date(value: Any) -> str:
    text = str(value or "").strip()
    return text[:10] if len(text) >= 10 else text


def _fmt_count(value: Any) -> str:
    """户数：沿用股数万/亿写法（如 29.64万）。"""
    return fmt_shares(value)


def _fmt_signed_count(value: Any) -> str:
    number = to_float(value)
    if number is None:
        return ""
    pretty = _fmt_count(abs(number))
    if not pretty:
        return ""
    if number > 0:
        return f"+{pretty}"
    if number < 0:
        return f"-{pretty}"
    return pretty


def _dc_page(code: str, *, page: int = 1, page_size: int = _PAGE_SIZE) -> dict[str, Any]:
    payload = get_json(
        _API,
        params={
            "sortColumns": "END_DATE",
            "sortTypes": "-1",
            "pageSize": str(page_size),
            "pageNumber": str(page),
            "reportName": _REPORT,
            "columns": "ALL",
            "filter": f'(SECURITY_CODE="{code}")',
            "source": "WEB",
            "client": "WEB",
        },
        headers=_HEADERS,
        timeout=(6, 25),
        retries=1,
    )
    if not isinstance(payload, dict) or not payload.get("success"):
        message = str((payload or {}).get("message") or "东财股东户数接口失败")
        raise RuntimeError(message)
    result = payload.get("result")
    if not isinstance(result, dict):
        raise RuntimeError("东财股东户数返回格式异常")
    return result


def _parse_row(row: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    day = _date(row.get("END_DATE"))
    holder_num = to_float(row.get("HOLDER_NUM"))
    if not day or holder_num is None:
        return None
    change = to_float(row.get("HOLDER_NUM_CHANGE"))
    change_ratio = to_float(row.get("HOLDER_NUM_RATIO"))
    avg_hold = to_float(row.get("AVG_HOLD_NUM"))
    avg_mcap = to_float(row.get("AVG_MARKET_CAP"))
    return {
        "time": day,
        "holder_num": int(holder_num) if holder_num == int(holder_num) else holder_num,
        "holder_num_fmt": _fmt_count(holder_num),
        "pre_holder_num": to_float(row.get("PRE_HOLDER_NUM")),
        "change": change,
        "change_fmt": _fmt_signed_count(change),
        "change_ratio": change_ratio,
        "change_ratio_fmt": fmt_pct(change_ratio),
        "avg_hold_num": avg_hold,
        "avg_hold_num_fmt": _fmt_count(avg_hold),
        "avg_market_cap": avg_mcap,
        "avg_market_cap_fmt": fmt_yi_wan(avg_mcap),
        "total_a_shares": to_float(row.get("TOTAL_A_SHARES")),
        "total_a_shares_fmt": fmt_shares(row.get("TOTAL_A_SHARES")),
        "notice_date": _date(row.get("HOLD_NOTICE_DATE")),
        "close": to_float(row.get("CLOSE_PRICE")),
        "interval_chrate": to_float(row.get("INTERVAL_CHRATE")),
        "interval_chrate_fmt": fmt_pct(row.get("INTERVAL_CHRATE")),
    }


def fetch_holder_num(
    code: str,
    *,
    limit: int = _DEFAULT_LIMIT,
    force: bool = False,
) -> dict[str, Any]:
    """拉取一家公司的股东户数序列（按报告期，时间升序）。"""
    code = normalize_code(code)
    if not code:
        raise ValueError("缺少股票代码")

    cap = max(1, min(int(limit or _DEFAULT_LIMIT), _PAGE_SIZE * _MAX_PAGES))
    cache_key = f"holder_num:{code}:{cap}"
    if not force:
        cached = _cache.get(cache_key)
        if cached:
            return dict(cached)

    raw_rows: list[dict[str, Any]] = []
    name = ""
    pages = 1
    page = 1
    last_exc: Exception | None = None

    while page <= pages and page <= _MAX_PAGES and len(raw_rows) < cap:
        try:
            result = _dc_page(code, page=page, page_size=min(_PAGE_SIZE, cap))
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.info("holder num skip %s page %s: %s", code, page, exc)
            break
        if page == 1:
            try:
                pages = max(1, int(result.get("pages") or 1))
            except (TypeError, ValueError):
                pages = 1
        data = result.get("data") or []
        if not data:
            break
        if not name and isinstance(data[0], dict):
            name = str(data[0].get("SECURITY_NAME_ABBR") or "").strip()
        raw_rows.extend(row for row in data if isinstance(row, dict))
        page += 1

    if not raw_rows and last_exc:
        raise last_exc

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    # 接口按 END_DATE 降序；图表要升序
    for row in reversed(raw_rows):
        parsed = _parse_row(row)
        if not parsed:
            continue
        day = parsed["time"]
        if day in seen:
            continue
        seen.add(day)
        items.append(parsed)

    if len(items) > cap:
        items = items[-cap:]

    latest = items[-1] if items else None
    payload = {
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "code": code,
        "name": name,
        "label": "股东户数",
        "source": "eastmoney" if items else "",
        "count": len(items),
        "latest": latest,
        "items": items,
    }
    _cache.put(cache_key, payload)
    return payload
