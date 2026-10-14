"""目标日 OHLC 在区间同类价格中的位置（同类比较 + 前复权）。

数据源复用 ``company.line.fetcher.fetch_kline``（period=day, adjust=qfq）。
输出 8 个核心数据：O/H/L/C 各一个排名 + 一个百分比，总数 N 附带返回。
排名方向由 order 控制，百分比统一为从小到大百分位（0%=最小，100%=最大）。
"""
from __future__ import annotations

from company.line.fetcher import fetch_kline

FIELDS = ("open", "high", "low", "close")


def _norm_date(s: str) -> str:
    return str(s or "")[:10].replace("/", "-").strip()


def _load_bars(symbol: str, start: str, end: str) -> list[dict]:
    pack = fetch_kline(symbol, period="day", adjust="qfq", limit=10000, beg=start, end=end)
    items = [b for b in (pack.get("items") or []) if isinstance(b, dict)]
    rows = []
    for b in items:
        d = _norm_date(b.get("time"))
        if not d or (start and d < start) or (end and d > end):
            continue
        try:
            rows.append({
                "date": d,
                "open": round(float(b["open"]), 4),
                "high": round(float(b["high"]), 4),
                "low": round(float(b["low"]), 4),
                "close": round(float(b["close"]), 4),
            })
        except (KeyError, TypeError, ValueError):
            continue
    rows.sort(key=lambda r: r["date"])
    return rows


def _calc_one(values: list[float], p: float, order: str) -> tuple[int, float, int, int]:
    n_less = sum(1 for v in values if v < p)
    n_greater = sum(1 for v in values if v > p)
    n = len(values)
    pct = 50.0 if n <= 1 else round(n_less / (n - 1) * 100, 2)
    rank = (n_less + 1) if order == "asc" else (n_greater + 1)
    return rank, pct, n_less, n_greater


def price_position(symbol: str, start_date: str, end_date: str, target_date: str, order: str = "desc") -> dict:
    """计算目标日 O/H/L/C 在区间同类价格中的排名与百分比。"""
    order = (order or "desc").strip().lower()
    if order not in ("asc", "desc"):
        raise ValueError("order 须为 asc(从小到大) 或 desc(从大到小)")
    start = _norm_date(start_date)
    end = _norm_date(end_date)
    target = _norm_date(target_date)
    if not start or not end or not target:
        raise ValueError("start_date/end_date/target_date 不能为空")
    if start > end:
        raise ValueError("start_date 不能晚于 end_date")

    rows = _load_bars(symbol, start, end)
    if not rows:
        raise ValueError(f"{symbol} 在 {start}~{end} 无交易日数据")
    dates = [r["date"] for r in rows]
    real_target = target
    substituted = False
    if target not in dates:
        prev = [d for d in dates if d < target]
        if target < start or target > end or not prev:
            raise ValueError(f"目标日 {target} 不在区间交易日列表内")
        real_target = prev[-1]
        substituted = True

    row = next(r for r in rows if r["date"] == real_target)
    n = len(rows)
    result: dict = {}
    for col in FIELDS:
        vals = [r[col] for r in rows]
        rank, pct, n_less, n_greater = _calc_one(vals, row[col], order)
        rank_asc = n_less + 1
        rank_desc = n_greater + 1
        result[col] = {
            "value": row[col],
            "rank": rank_desc if order == "desc" else rank_asc,
            "rank_asc": rank_asc,
            "rank_desc": rank_desc,
            "total": n,
            "percent": pct,
            "order": order,
        }
    return {
        "symbol": symbol, "adjust": "qfq", "method": "same_type",
        "start": start, "end": end,
        "target": real_target, "target_requested": target,
        "substituted": substituted, "N": n,
        "order": order,
        "target_ohlc": {k: row[k] for k in FIELDS},
        "result": result,
        "note": ("百分比统一为从小到大百分位；rank 受 order 影响，"
                 "rank_asc=从小到大第几(1=最小)，rank_desc=从大到小第几(1=最大)"),
    }
