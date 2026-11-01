"""个股某一交易日的四价「前低」回溯。

输入：股票代码 + 某交易日 → 取当日开盘 / 收盘 / 最高 / 最低四个价格。
对每个价格，往前回溯最近的、该价格「严格低于」当日同价的那个交易日，
返回那一天的日期以及两者之间间隔的交易日数量。

- 日线数据统一走系统现有入口 ``company.line.fetcher.fetch_kline``（前复权）。
- 回溯所需历史从该交易日往前翻页补齐，直到上市（无更早数据）为止。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from core.codes import normalize_code
from core.fmt import to_float

# 四价口径，顺序固定，前端按此展示
FACTORS: tuple[str, ...] = ("open", "close", "high", "low")
FACTOR_LABELS: dict[str, str] = {
    "open": "开盘价",
    "close": "收盘价",
    "high": "最高价",
    "low": "最低价",
}


def _iso(value: str) -> str:
    """``YYYYMMDD`` / ``YYYY-MM-DD`` / ``YYYY/MM/DD`` → ``YYYY-MM-DD``。"""
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if len(digits) < 8:
        raise ValueError(f"日期须为 YYYYMMDD 或 YYYY-MM-DD，收到 {value!r}")
    return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"


def _bar_date(bar: dict[str, Any]) -> str:
    return str(bar.get("time") or "")[:10]


def _find_prior_lower(
    bars: list[dict[str, Any]],
    idx: int,
    factor: str,
    target_price: float,
) -> dict[str, Any] | None:
    """从 idx 往前找最近的、同因子价格严格低于 target_price 的交易日。"""
    for j in range(idx - 1, -1, -1):
        prev = to_float(bars[j].get(factor))
        if prev is None:
            continue
        if prev < target_price:
            found_date = _bar_date(bars[j])
            return {
                "date": found_date,
                "found_price": prev,
                # 中间间隔的交易日（不含两端）
                "gap": idx - j - 1,
                # 相隔的交易日位置差（含一段跨度）
                "sessions": idx - j,
            }
    return None


def compute_extremum(
    bars: list[dict[str, Any]],
    target_date: str,
) -> dict[str, Any]:
    """在已排序的日线序列上做「前低」回溯（纯函数，便于单测）。

    target_date：``YYYY-MM-DD`` 或 ``YYYYMMDD``。若该日非交易日，
    自动取不晚于它的最近一个交易日。
    """
    if not bars:
        raise ValueError("无日线数据")

    target_iso = _iso(target_date)
    ordered = sorted(bars, key=_bar_date)

    idx: int | None = None
    for i in range(len(ordered) - 1, -1, -1):
        if _bar_date(ordered[i]) and _bar_date(ordered[i]) <= target_iso:
            idx = i
            break
    if idx is None:
        raise ValueError(f"{target_iso} 之前无日线数据")

    bar = ordered[idx]
    used_date = _bar_date(bar)
    prices: dict[str, float | None] = {f: to_float(bar.get(f)) for f in FACTORS}

    extremum: dict[str, Any] = {}
    for factor in FACTORS:
        target_price = prices[factor]
        entry: dict[str, Any] = {
            "factor": factor,
            "label": FACTOR_LABELS[factor],
            "target_price": target_price,
            "date": None,
            "found_price": None,
            "gap": None,
            "sessions": None,
        }
        if target_price is not None:
            found = _find_prior_lower(ordered, idx, factor, target_price)
            if found is not None:
                entry.update(found)
        extremum[factor] = entry

    return {
        "date": used_date,
        "input_date": target_iso,
        "snapped": used_date != target_iso,
        "prices": dict(prices),
        "extremum": extremum,
    }


def _all_found(items: list[dict[str, Any]], target_iso: str) -> bool:
    """四价是否都已找到更低的更早交易日；找到即可停止继续往前翻页。"""
    if not items:
        return False
    packed = compute_extremum(items, target_iso)
    return all(
        (packed["extremum"][f] or {}).get("date") is not None for f in FACTORS
    )


def _fetch_history(code: str, *, end_iso: str, adjust: str = "qfq") -> dict[str, Any]:
    """从该交易日往前翻页拉日线，四价都找到更早低点即停，否则到上市为止。"""
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
        # 已有足够历史（四价都找到更早低点）则无需再往前翻
        if _all_found(items, end_iso):
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


def analyze_extremum(
    code: str,
    date: str,
    *,
    adjust: str = "qfq",
) -> dict[str, Any]:
    """主入口：某只股票某交易日的四价前低回溯（前复权日线）。"""
    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")
    target_iso = _iso(date)

    hist = _fetch_history(norm, end_iso=target_iso, adjust=adjust)
    result = compute_extremum(list(hist.get("items") or []), target_iso)

    return {
        "code": norm,
        "name": str(hist.get("name") or ""),
        "source": str(hist.get("source") or ""),
        "adjust": adjust,
        **result,
    }
