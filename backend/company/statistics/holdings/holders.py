"""个股前十大股东：东财 ``RPT_F10_EH_HOLDERS`` / ``RPT_F10_EH_FREEHOLDERS``。"""

from __future__ import annotations

import logging
import time
from typing import Any

from core.cache import TtlCache
from core.codes import normalize_code
from core.fmt import fmt_list_date, fmt_pct, fmt_shares, fmt_yi_wan, to_float
from core.http import get_json

logger = logging.getLogger(__name__)

_API = "https://datacenter-web.eastmoney.com/api/data/v1/get"
_HEADERS = {"Referer": "https://data.eastmoney.com/"}
_CACHE_TTL = 6 * 60 * 60
_TOP_N = 10
_DATE_LOOKBACK = 16

_REPORTS = {
    "holders": "RPT_F10_EH_HOLDERS",
    "free": "RPT_F10_EH_FREEHOLDERS",
}

_cache = TtlCache(_CACHE_TTL)


def _date(value: Any) -> str:
    text = str(value or "").strip()
    return text[:10] if len(text) >= 10 else text


def _dc_page(
    code: str,
    *,
    report_name: str,
    report_date: str | None = None,
    page: int = 1,
    page_size: int = _TOP_N,
    sort_columns: str = "HOLDER_RANK",
    sort_types: str = "1",
) -> dict[str, Any]:
    filt = f'(SECURITY_CODE="{code}")'
    if report_date:
        filt += f"(END_DATE='{report_date}')"
    payload = get_json(
        _API,
        params={
            "sortColumns": sort_columns,
            "sortTypes": sort_types,
            "pageSize": str(page_size),
            "pageNumber": str(page),
            "reportName": report_name,
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
        message = str((payload or {}).get("message") or "东财十大股东接口失败")
        raise RuntimeError(message)
    result = payload.get("result")
    if not isinstance(result, dict):
        raise RuntimeError("东财十大股东返回格式异常")
    return result


def _change(value: Any) -> tuple[float | None, str]:
    text = str(value or "").strip()
    number = to_float(value)
    if number is not None:
        pretty = fmt_shares(number)
        if number > 0:
            pretty = f"+{pretty}"
        elif number < 0:
            pretty = f"-{pretty}"
        return number, pretty
    if text in {"", "-", "--", "None", "null"}:
        return None, ""
    return None, text


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    shares = to_float(row.get("HOLD_NUM"))
    ratio = to_float(row.get("HOLD_NUM_RATIO"))
    if ratio is None:
        ratio = to_float(row.get("FREE_HOLDNUM_RATIO"))
    change_raw, change_fmt = _change(row.get("HOLD_NUM_CHANGE"))
    market_cap = to_float(row.get("HOLDER_MARKET_CAP"))
    rank = to_float(row.get("HOLDER_RANK"))
    return {
        "rank": int(rank) if rank is not None else None,
        "name": str(row.get("HOLDER_NAME") or row.get("HOLD_NUM_ABBR") or "").strip(),
        "holder_code": str(row.get("HOLDER_CODE") or "").strip(),
        "holder_type": str(row.get("HOLDER_TYPE") or "").strip(),
        "shares_type": str(row.get("SHARES_TYPE") or "").strip(),
        "is_org": str(row.get("IS_HOLDORG") or "").strip() == "1",
        "status": str(row.get("HOLDER_STATE_NEW") or row.get("HOLDER_STATE") or "").strip(),
        "shares": shares,
        "shares_fmt": fmt_shares(shares),
        "ratio": ratio,
        "ratio_fmt": fmt_pct(ratio),
        "change": change_raw,
        "change_fmt": change_fmt,
        "change_ratio": to_float(row.get("CHANGE_RATIO")),
        "change_ratio_fmt": fmt_pct(row.get("CHANGE_RATIO")),
        "market_value": market_cap,
        "market_value_fmt": fmt_yi_wan(market_cap),
        "report_date": _date(row.get("END_DATE")),
    }


def _rows_of_date(rows: list[Any], report_date: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if _date(row.get("END_DATE")) != report_date:
            continue
        items.append(_normalize_row(row))
    items.sort(key=lambda item: (item.get("rank") is None, item.get("rank") or 0))
    return items[:_TOP_N]


def _unique_dates(rows: list[Any], *, limit: int = _DATE_LOOKBACK) -> list[str]:
    dates: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        day = _date(row.get("END_DATE"))
        if not day or day in seen:
            continue
        seen.add(day)
        dates.append(day)
        if len(dates) >= limit:
            break
    return dates


def _dates_key(kind: str, code: str) -> str:
    return f"{kind}:{code}:dates"


def _merge_dates(*groups: list[Any]) -> list[str]:
    dates: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for raw in group or []:
            day = _date(raw)
            if not day or day in seen:
                continue
            seen.add(day)
            dates.append(day)
    dates.sort(reverse=True)
    return dates[:_DATE_LOOKBACK]


def _remember_dates(kind: str, code: str, dates: list[str]) -> list[str]:
    cached = _cache.get(_dates_key(kind, code))
    merged = _merge_dates(dates, cached if isinstance(cached, list) else [])
    if merged:
        _cache.put(_dates_key(kind, code), list(merged))
    return merged


def _load_report_dates(
    code: str,
    report_name: str,
    kind: str,
    *,
    force: bool = False,
) -> list[str]:
    dates_key = _dates_key(kind, code)
    if not force:
        cached = _cache.get(dates_key)
        if isinstance(cached, list) and cached:
            return list(cached)
        latest = _cache.get(f"{kind}:{code}:latest")
        if isinstance(latest, dict):
            cached_dates = latest.get("report_dates") or []
            if cached_dates:
                return _remember_dates(kind, code, list(cached_dates))
    try:
        result = _dc_page(
            code,
            report_name=report_name,
            page_size=_DATE_LOOKBACK * _TOP_N,
            sort_columns="END_DATE,HOLDER_RANK",
            sort_types="-1,1",
        )
    except Exception:
        logger.warning("十大股东报告期列表失败 %s", code, exc_info=True)
        return []
    return _remember_dates(kind, code, _unique_dates(result.get("data") or []))


def fetch_top_holders(
    code: str,
    *,
    report_date: str | None = None,
    scope: str = "holders",
    force: bool = False,
) -> dict[str, Any]:
    """拉取一家公司某一报告期的前十大股东（按持股排名）。

    ``scope=holders`` 十大股东；``scope=free`` 十大流通股东。
    """
    code = normalize_code(code)
    if not code:
        raise ValueError("缺少股票代码")

    kind = (scope or "holders").strip().lower()
    if kind in {"sdgd", "top", "top10"}:
        kind = "holders"
    if kind in {"sdltgd", "float", "lt"}:
        kind = "free"
    report_name = _REPORTS.get(kind)
    if not report_name:
        raise ValueError("scope 仅支持 holders 或 free")

    wanted = fmt_list_date((report_date or "").strip())
    cache_key = f"{kind}:{code}:{wanted or 'latest'}"
    if not force:
        cached = _cache.get(cache_key)
        if cached:
            cached = dict(cached)
            cached["report_dates"] = _remember_dates(
                kind, code, list(cached.get("report_dates") or [])
            )
            return cached

    dates: list[str] = []
    name = ""
    total_shares = None
    if wanted:
        result = _dc_page(
            code,
            report_name=report_name,
            report_date=wanted,
            page_size=_TOP_N,
            sort_columns="HOLDER_RANK",
            sort_types="1",
        )
        raw_rows = result.get("data") or []
        date = wanted
        items = _rows_of_date(raw_rows, date)
        dates = _remember_dates(
            kind,
            code,
            [date, *_load_report_dates(code, report_name, kind, force=force)],
        )
        if raw_rows and isinstance(raw_rows[0], dict):
            name = str(raw_rows[0].get("SECURITY_NAME_ABBR") or "").strip()
            total_shares = to_float(raw_rows[0].get("TOTAL_SHARES_NUM"))
    else:
        result = _dc_page(
            code,
            report_name=report_name,
            page_size=_DATE_LOOKBACK * _TOP_N,
            sort_columns="END_DATE,HOLDER_RANK",
            sort_types="-1,1",
        )
        raw_rows = result.get("data") or []
        dates = _remember_dates(kind, code, _unique_dates(raw_rows))
        if not dates:
            raise RuntimeError("暂无十大股东报告期")
        date = dates[0]
        items = _rows_of_date(raw_rows, date)
        for row in raw_rows:
            if isinstance(row, dict) and _date(row.get("END_DATE")) == date:
                name = str(row.get("SECURITY_NAME_ABBR") or "").strip()
                total_shares = to_float(row.get("TOTAL_SHARES_NUM"))
                break

    if not items:
        raise RuntimeError("暂无十大股东数据")

    label = "十大流通股东" if kind == "free" else "十大股东"
    payload = {
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "code": code,
        "name": name,
        "scope": kind,
        "label": label,
        "report_date": date,
        "report_dates": dates,
        "count": len(items),
        "total_shares": total_shares,
        "total_shares_fmt": fmt_shares(total_shares),
        "items": items,
        "source": "eastmoney",
    }
    _cache.put(cache_key, payload)
    return payload
