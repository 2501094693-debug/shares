"""最新交易日收盘价 / 最低价的「最近最低」回溯。

输入：一只股票。取最新交易日的收盘价与最低价，各自往前回溯，
统计该价格是最近多少个交易日的最低（窗口内无严格更低的同口径价）。

- 相等仍计入窗口（遇严格更低才停）。
- ``days`` 含最新交易日本身；若上市以来无更低，则为全部可用交易日数。
- 日线走 ``company.line.fetcher.fetch_kline``（默认前复权），
  往前翻页直到两口径都找到更低日或上市为止。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from core.codes import normalize_code
from core.fmt import to_float

from company.analysis.line.prior_low import _bar_date, _iso

FACTORS: tuple[str, ...] = ("close", "low")
FACTOR_LABELS: dict[str, str] = {
    "close": "收盘价",
    "low": "最低价",
}


def _lookback_as_low(
    bars: list[dict[str, Any]],
    idx: int,
    factor: str,
    target_price: float,
) -> dict[str, Any]:
    """从 idx 往前数：target 是最近多少个交易日的最低价。"""
    prior_date: str | None = None
    prior_price: float | None = None
    stop_j = -1
    for j in range(idx - 1, -1, -1):
        prev = to_float(bars[j].get(factor))
        if prev is None:
            continue
        if prev < target_price:
            prior_date = _bar_date(bars[j])
            prior_price = prev
            stop_j = j
            break

    # 窗口 [stop_j+1, idx]；无更低则从 0 起
    start_j = stop_j + 1
    while start_j <= idx and to_float(bars[start_j].get(factor)) is None:
        start_j += 1
    days = idx - start_j + 1 if start_j <= idx else 0
    return {
        "factor": factor,
        "label": FACTOR_LABELS[factor],
        "price": target_price,
        "days": days,
        "since": _bar_date(bars[start_j]) if days > 0 else None,
        "prior_lower_date": prior_date,
        "prior_lower_price": prior_price,
        "is_all_time_low": prior_date is None,
    }


def compute_recent_low(bars: list[dict[str, Any]]) -> dict[str, Any]:
    """在已排序日线上，对最新交易日的收盘 / 最低做回溯（纯函数）。"""
    if not bars:
        raise ValueError("无日线数据")

    ordered = sorted(bars, key=_bar_date)
    idx = len(ordered) - 1
    bar = ordered[idx]
    used_date = _bar_date(bar)
    prices: dict[str, float | None] = {f: to_float(bar.get(f)) for f in FACTORS}

    result: dict[str, Any] = {}
    for factor in FACTORS:
        target = prices[factor]
        if target is None:
            result[factor] = {
                "factor": factor,
                "label": FACTOR_LABELS[factor],
                "price": None,
                "days": None,
                "since": None,
                "prior_lower_date": None,
                "prior_lower_price": None,
                "is_all_time_low": None,
            }
            continue
        result[factor] = _lookback_as_low(ordered, idx, factor, target)

    return {
        "date": used_date,
        "prices": dict(prices),
        "lookback": result,
        "history_count": len(ordered),
    }


def _both_found(items: list[dict[str, Any]]) -> bool:
    if not items:
        return False
    packed = compute_recent_low(items)
    lookback = packed.get("lookback") or {}
    return all(
        (lookback.get(f) or {}).get("prior_lower_date") is not None for f in FACTORS
    )


def _fetch_history(code: str, *, adjust: str = "qfq") -> dict[str, Any]:
    """从最新交易日往前翻页，收盘/最低都找到更低日即停，否则到上市。"""
    from company.line.fetcher import fetch_kline

    items: list[dict[str, Any]] = []
    source = ""
    name = ""
    cur_end = datetime.now().strftime("%Y%m%d")
    pack: dict[str, Any] = {}

    for _ in range(80):
        pack = fetch_kline(
            code,
            period="day",
            adjust=adjust,
            end=cur_end,
            limit=2000,
        )
        page = list(pack.get("items") or [])
        if not page:
            break
        source = str(pack.get("source") or source)
        name = str(pack.get("name") or name)

        have = {_bar_date(b) for b in items if _bar_date(b)}
        fresh = [b for b in page if _bar_date(b) and _bar_date(b) not in have]
        if not fresh:
            break
        items = fresh + items

        if pack.get("full_history"):
            break
        if _both_found(items):
            break
        first = _bar_date(page[0])
        if not first:
            break
        try:
            cur_end = (
                datetime.strptime(first, "%Y-%m-%d") - timedelta(days=1)
            ).strftime("%Y%m%d")
        except ValueError:
            break

    items.sort(key=_bar_date)
    return {
        "code": str(pack.get("code") or code),
        "name": name,
        "source": source,
        "items": items,
    }


def analyze_recent_low(
    code: str,
    *,
    adjust: str = "qfq",
    end: str = "",
) -> dict[str, Any]:
    """主入口：一只股票最新（或指定截止日）收盘/最低价的最近最低回溯。"""
    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")

    if end:
        # 指定截止日时，沿用 prior_low 的翻页逻辑但只取到该日
        end_iso = _iso(end)
        hist = _fetch_history_until(norm, end_iso=end_iso, adjust=adjust)
        items = [b for b in (hist.get("items") or []) if _bar_date(b) <= end_iso]
    else:
        hist = _fetch_history(norm, adjust=adjust)
        items = list(hist.get("items") or [])

    if not items:
        raise ValueError("无日线数据")

    result = compute_recent_low(items)
    return {
        "code": norm,
        "name": str(hist.get("name") or ""),
        "source": str(hist.get("source") or ""),
        "adjust": adjust,
        **result,
    }


def _fetch_history_until(
    code: str,
    *,
    end_iso: str,
    adjust: str = "qfq",
) -> dict[str, Any]:
    """从指定截止日往前翻页（便于单测/指定交易日）。"""
    from company.line.fetcher import fetch_kline

    end_compact = end_iso.replace("-", "")
    items: list[dict[str, Any]] = []
    source = ""
    name = ""
    cur_end = end_compact
    pack: dict[str, Any] = {}

    for _ in range(80):
        pack = fetch_kline(
            code,
            period="day",
            adjust=adjust,
            end=cur_end,
            limit=2000,
        )
        page = list(pack.get("items") or [])
        if not page:
            break
        source = str(pack.get("source") or source)
        name = str(pack.get("name") or name)

        have = {_bar_date(b) for b in items if _bar_date(b)}
        fresh = [b for b in page if _bar_date(b) and _bar_date(b) not in have]
        if not fresh:
            break
        items = fresh + items

        if pack.get("full_history"):
            break
        # 先裁到截止日再判断是否已找到更低
        clipped = [b for b in items if _bar_date(b) <= end_iso]
        if _both_found(clipped):
            break
        first = _bar_date(page[0])
        if not first:
            break
        try:
            cur_end = (
                datetime.strptime(first, "%Y-%m-%d") - timedelta(days=1)
            ).strftime("%Y%m%d")
        except ValueError:
            break

    items.sort(key=_bar_date)
    return {
        "code": str(pack.get("code") or code),
        "name": name,
        "source": source,
        "items": items,
    }
