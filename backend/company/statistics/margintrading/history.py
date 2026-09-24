"""个股融资融券走势：东财 ``RPTA_WEB_RZRQ_GGMX``。

按交易日给出融资/融券余额、净买入、余额占流通市值比等，供前端画走势图。

    python -m company.statistics.margintrading 600519
    python -m company.statistics.margintrading 600519 --limit 10 --json
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
_REPORT = "RPTA_WEB_RZRQ_GGMX"
_HEADERS = {"Referer": "https://data.eastmoney.com/"}
_CACHE_TTL = 10 * 60
_PAGE_SIZE = 500
_MAX_PAGES = 6
_DEFAULT_LIMIT = 1500

_cache = TtlCache(_CACHE_TTL)


def _date(value: Any) -> str:
    text = str(value or "").strip()
    return text[:10] if len(text) >= 10 else text


def _fmt_signed_yi(value: Any) -> str:
    number = to_float(value)
    if number is None:
        return ""
    pretty = fmt_yi_wan(abs(number))
    if not pretty:
        return ""
    if number > 0:
        return f"+{pretty}"
    if number < 0:
        return f"-{pretty}"
    return pretty


def _fmt_signed_shares(value: Any) -> str:
    number = to_float(value)
    if number is None:
        return ""
    pretty = fmt_shares(abs(number))
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
            "sortColumns": "DATE",
            "sortTypes": "-1",
            "pageSize": str(page_size),
            "pageNumber": str(page),
            "reportName": _REPORT,
            "columns": "ALL",
            "filter": f'(SCODE="{code}")',
            "source": "WEB",
            "client": "WEB",
        },
        headers=_HEADERS,
        timeout=(6, 25),
        retries=1,
    )
    if not isinstance(payload, dict) or not payload.get("success"):
        message = str((payload or {}).get("message") or "东财融资融券接口失败")
        raise RuntimeError(message)
    result = payload.get("result")
    if not isinstance(result, dict):
        raise RuntimeError("东财融资融券返回格式异常")
    return result


def _parse_row(row: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    day = _date(row.get("DATE") or row.get("TRADE_DATE"))
    rzye = to_float(row.get("RZYE"))
    rzrqye = to_float(row.get("RZRQYE"))
    rqye = to_float(row.get("RQYE"))
    if not day or (rzye is None and rzrqye is None and rqye is None):
        return None
    rzjme = to_float(row.get("RZJME"))
    rzmre = to_float(row.get("RZMRE"))
    rzche = to_float(row.get("RZCHE"))
    rzyezb = to_float(row.get("RZYEZB"))
    rqyl = to_float(row.get("RQYL"))
    rqmcl = to_float(row.get("RQMCL"))
    # 融券净卖出：股数（卖出量 − 偿还量），东财字段 RQJMG
    rqjmg = to_float(row.get("RQJMG"))
    return {
        "time": day,
        "rzye": rzye,
        "rzye_fmt": fmt_yi_wan(rzye),
        "rqye": rqye,
        "rqye_fmt": fmt_yi_wan(rqye),
        "rzrqye": rzrqye,
        "rzrqye_fmt": fmt_yi_wan(rzrqye),
        "rzjme": rzjme,
        "rzjme_fmt": _fmt_signed_yi(rzjme),
        "rzmre": rzmre,
        "rzmre_fmt": fmt_yi_wan(rzmre),
        "rzche": rzche,
        "rzche_fmt": fmt_yi_wan(rzche),
        "rqyl": rqyl,
        "rqyl_fmt": fmt_shares(rqyl),
        "rqmcl": rqmcl,
        "rqmcl_fmt": fmt_shares(rqmcl),
        "rqjmg": rqjmg,
        "rqjmg_fmt": _fmt_signed_shares(rqjmg),
        "rzyezb": rzyezb,
        "rzyezb_fmt": fmt_pct(rzyezb),
        "close": to_float(row.get("SPJ")),
        "pct_chg": to_float(row.get("ZDF")),
    }


def fetch_margin_trading(
    code: str,
    *,
    limit: int = _DEFAULT_LIMIT,
    force: bool = False,
) -> dict[str, Any]:
    """拉取一家公司的融资融券日序列（时间升序）。"""
    code = normalize_code(code)
    if not code:
        raise ValueError("缺少股票代码")

    cap = max(1, min(int(limit or _DEFAULT_LIMIT), _PAGE_SIZE * _MAX_PAGES))
    cache_key = f"margin_trading:{code}:{cap}"
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
            logger.info("margin trading skip %s page %s: %s", code, page, exc)
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
            name = str(data[0].get("SECNAME") or "").strip()
        raw_rows.extend(row for row in data if isinstance(row, dict))
        page += 1

    if not raw_rows and last_exc:
        raise last_exc

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    # 接口按 DATE 降序；图表要升序
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
        "label": "融资融券",
        "source": "eastmoney" if items else "",
        "count": len(items),
        "latest": latest,
        "items": items,
    }
    _cache.put(cache_key, payload)
    return payload
