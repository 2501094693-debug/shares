"""同花顺个股最近 N 个交易日的分时成交（默认五日，秒级）。

拼装策略（都走同花顺，不掺东财/腾讯）：

1. 用日 K 取最近 ``days`` 个交易日；
2. 每个交易日的**秒级成交**：
   - 当日：优先 ``thsdk`` 全日切片；失败再 ``single_trace`` 尾部；
   - 历史日：先读本机逐笔磁盘缓存（若盘中曾落盘）；否则 ``single_trace`` 尾部
     （免费通道约 500 档，不是全天，``incomplete=True``）；
3. 同步附带各日分钟分时（``single_trend``），对应 App「五日」曲线底图。
"""

from __future__ import annotations

import logging
from typing import Any

from core.codes import normalize_code
from company.line.session import session_day
from company.line.fivedays.ths import (
    TRACE_PAGE,
    ThsMobileError,
    fetch_day_ticks_thsdk,
    fetch_day_trace,
    fetch_day_trend,
)

logger = logging.getLogger(__name__)

DEFAULT_DAYS = 5


def last_trading_days(code: str, days: int = DEFAULT_DAYS) -> list[str]:
    """最近 ``days`` 个交易日（升序），来源日 K。"""
    from company.line.fetcher import fetch_kline

    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")
    n = max(1, min(int(days), 30))
    pack = fetch_kline(norm, period="day", adjust="none", limit=max(n + 2, n))
    items = list(pack.get("items") or [])
    out: list[str] = []
    for row in items:
        if not isinstance(row, dict):
            continue
        text = str(row.get("time") or "")[:10]
        if len(text) == 10 and text[4] == "-":
            out.append(text)
    # 去重保序，取尾部 N 日
    uniq: list[str] = []
    seen: set[str] = set()
    for day in out:
        if day in seen:
            continue
        seen.add(day)
        uniq.append(day)
    return uniq[-n:]


def _load_disk_ticks(code: str, day: str) -> list[dict[str, Any]]:
    """历史日只读本机逐笔缓存；没有则空。"""
    from company.line.fetcher import fetch_ticks

    pack = fetch_ticks(code, pos=0, day=day)
    if not isinstance(pack, dict):
        return []
    if pack.get("error"):
        return []
    items = pack.get("items") or []
    return [row for row in items if isinstance(row, dict)]


def _fetch_day_seconds(code: str, day: str) -> dict[str, Any]:
    today = session_day().isoformat()
    source = ""
    incomplete = False
    items: list[dict[str, Any]] = []
    note = ""

    if day == today:
        try:
            items = fetch_day_ticks_thsdk(code, day)
            if items:
                source = "thsdk:ticks"
        except Exception as exc:  # noqa: BLE001
            note = f"thsdk 当日秒级失败: {exc}"
            logger.info("fivedays thsdk skip %s %s: %s", code, day, exc)

    if not items:
        cached = _load_disk_ticks(code, day)
        if cached:
            items = cached
            source = "disk_cache"
        else:
            try:
                items = fetch_day_trace(code, day, count=TRACE_PAGE)
                source = "ths_mobile_trace"
                # 免费通道拿不到早盘，标 incomplete
                if items:
                    first = str(items[0].get("time") or "")
                    incomplete = first[11:16] > "09:30"
                else:
                    incomplete = True
                    note = note or "single_trace 空"
            except ThsMobileError as exc:
                incomplete = True
                note = str(exc)
                logger.info("fivedays trace fail %s %s: %s", code, day, exc)

    return {
        "day": day,
        "source": source,
        "incomplete": incomplete,
        "count": len(items),
        "items": items,
        "note": note,
        "last_time": items[-1].get("time") if items else "",
        "last_price": items[-1].get("price") if items else None,
    }


def _fetch_day_minutes(code: str, day: str) -> dict[str, Any]:
    try:
        pack = fetch_day_trend(code, day)
    except Exception as exc:  # noqa: BLE001
        logger.info("fivedays trend fail %s %s: %s", code, day, exc)
        return {
            "day": day,
            "source": "",
            "count": 0,
            "items": [],
            "pre_price": None,
            "note": str(exc),
        }
    return {
        "day": pack.get("day") or day,
        "source": "ths_mobile_trend",
        "count": int(pack.get("count") or 0),
        "items": list(pack.get("items") or []),
        "pre_price": pack.get("pre_price"),
        "note": "",
    }


def fetch_fivedays(
    code: str,
    *,
    days: int = DEFAULT_DAYS,
    include_trend: bool = True,
) -> dict[str, Any]:
    """拉取最近 ``days`` 个交易日的同花顺分时成交（秒级）及可选分钟分时。

    返回::

        {
          "code", "days", "source": "tonghuashun",
          "count", "items",          # 五日秒级成交按时序拼在一起
          "by_day": {day: {...}},    # 每日秒级包
          "trends": {day: {...}},    # 每日分钟分时（include_trend 时）
          "notes": [...]
        }
    """
    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")
    n = max(1, min(int(days), 30))
    day_list = last_trading_days(norm, n)
    if not day_list:
        return {
            "code": norm,
            "days": [],
            "source": "tonghuashun",
            "count": 0,
            "items": [],
            "by_day": {},
            "trends": {},
            "notes": ["无交易日（日 K 为空）"],
        }

    by_day: dict[str, Any] = {}
    trends: dict[str, Any] = {}
    notes: list[str] = []
    all_items: list[dict[str, Any]] = []

    for day in day_list:
        pack = _fetch_day_seconds(norm, day)
        by_day[day] = pack
        all_items.extend(pack["items"])
        if pack.get("incomplete"):
            notes.append(
                f"{day} 秒级仅有尾部 {pack['count']} 档"
                f"（single_trace 上限约 {TRACE_PAGE}）"
            )
        if pack.get("note"):
            notes.append(f"{day}: {pack['note']}")
        if include_trend:
            trends[day] = _fetch_day_minutes(norm, day)

    all_items.sort(
        key=lambda r: (str(r.get("time") or ""), int(r.get("seq") or 0))
    )
    return {
        "code": norm,
        "days": day_list,
        "source": "tonghuashun",
        "count": len(all_items),
        "items": all_items,
        "by_day": by_day,
        "trends": trends,
        "notes": notes,
    }
