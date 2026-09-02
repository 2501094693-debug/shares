"""东财涨停池 / 跌停池：按交易日拉完整名单。"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from core.fmt import to_float
from core.http import get_json

_UT = "7eea3edcaed734bea9cbfc24409ed989"
_DPT = "wz.ztzt"
_BASE = "https://push2ex.eastmoney.com"
_HEADERS = {"Referer": "https://quote.eastmoney.com/ztb/"}
_PAGE_SIZE = 500

_ZT = ("getTopicZTPool", "fbt:asc")
_DT = ("getTopicDTPool", "fund:asc")


def _ymd(date: str | None = None) -> str:
    text = str(date or "").strip().replace("-", "")
    if len(text) == 8 and text.isdigit():
        return text
    return datetime.now().strftime("%Y%m%d")


def _name(value: Any) -> str:
    return "".join(str(value or "").split())


def _price(value: Any) -> float | None:
    number = to_float(value)
    if number is None:
        return None
    return round(number / 1000.0, 3)


def _fmt_time(value: Any) -> str:
    if value is None or value == "":
        return ""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return str(value).strip()
    text = f"{number:06d}"[-6:]
    return f"{text[0:2]}:{text[2:4]}:{text[4:6]}"


def _rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data") or {}
    pool = data.get("pool") or []
    if isinstance(pool, dict):
        pool = list(pool.values())
    return [item for item in pool if isinstance(item, dict)]


def _fetch(endpoint: str, sort: str, date: str) -> list[dict[str, Any]]:
    params = {
        "ut": _UT,
        "dpt": _DPT,
        "Pageindex": "0",
        "pagesize": str(_PAGE_SIZE),
        "sort": sort,
        "date": date,
        "_": str(int(time.time() * 1000)),
    }
    payload = get_json(
        f"{_BASE}/{endpoint}",
        params=params,
        headers=_HEADERS,
        timeout=(5, 12),
        retries=2,
    )
    if not isinstance(payload, dict):
        return []
    return _rows(payload)


def _base_row(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": str(item.get("c") or "").strip(),
        "name": _name(item.get("n")),
        "market": item.get("m"),
        "price": _price(item.get("p")),
        "change_pct": to_float(item.get("zdp")),
        "amount": to_float(item.get("amount")),
        "float_mv": to_float(item.get("ltsz")),
        "market_cap": to_float(item.get("tshare")),
        "turnover": to_float(item.get("hs")),
    }


def _parse_limit_up(item: dict[str, Any]) -> dict[str, Any] | None:
    row = _base_row(item)
    if not row["code"]:
        return None
    stat = item.get("zttj") if isinstance(item.get("zttj"), dict) else {}
    row.update(
        {
            "board_count": int(to_float(item.get("lbc")) or 0),
            "first_seal": _fmt_time(item.get("fbt")),
            "last_seal": _fmt_time(item.get("lbt")),
            "seal_fund": to_float(item.get("fund")),
            "break_count": int(to_float(item.get("zbc")) or 0),
            "stat_days": int(to_float(stat.get("days")) or 0),
            "stat_count": int(to_float(stat.get("ct")) or 0),
        }
    )
    return row


def _parse_limit_down(item: dict[str, Any]) -> dict[str, Any] | None:
    row = _base_row(item)
    if not row["code"]:
        return None
    row.update(
        {
            "down_days": int(to_float(item.get("days")) or 0),
            "open_count": int(to_float(item.get("oc")) or 0),
            "first_seal": _fmt_time(item.get("fbt")),
            "last_seal": _fmt_time(item.get("lbt")),
            "seal_fund": to_float(item.get("fund")),
            "break_count": int(
                to_float(item.get("zbc")) or to_float(item.get("oc")) or 0
            ),
            "board_amount": to_float(item.get("fba")),
            "pe": to_float(item.get("pe")),
        }
    )
    return row


def fetch_limit_up(date: str | None = None) -> list[dict[str, Any]]:
    """某日涨停名单，按连板数、首次封板时间排序。"""
    date = _ymd(date)
    rows = [_parse_limit_up(item) for item in _fetch(*_ZT, date)]
    out = [row for row in rows if row]
    out.sort(key=lambda r: (-r["board_count"], r["first_seal"] or "99"))
    return out


def fetch_limit_down(date: str | None = None) -> list[dict[str, Any]]:
    """某日跌停名单，按连续跌停天数、跌幅排序。"""
    date = _ymd(date)
    rows = [_parse_limit_down(item) for item in _fetch(*_DT, date)]
    out = [row for row in rows if row]
    out.sort(key=lambda r: (-r["down_days"], r.get("change_pct") if r.get("change_pct") is not None else 0))
    return out


def fetch_day_pools(date: str | None = None) -> dict[str, Any]:
    """某日涨停池 + 跌停池。"""
    date = _ymd(date)
    limit_up = fetch_limit_up(date)
    limit_down = fetch_limit_down(date)
    return {
        "date": f"{date[:4]}-{date[4:6]}-{date[6:8]}",
        "date_raw": date,
        "limit_up_count": len(limit_up),
        "limit_down_count": len(limit_down),
        "limit_up": limit_up,
        "limit_down": limit_down,
    }
