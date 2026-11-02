"""峰 / 谷评分。

对峰谷序列先拆成峰值序列与谷值序列，再各自打分，输出两条评分序列。

三维直接加总：

- **价格**（满分 ``W_PRICE``）
  - 组内相对线性：谷越低越高分，峰越高越高分
  - ``t ∈ [0, 1]`` 后 × ``W_PRICE``（组内全相同则满分）
- **天数**（满分 ``W_DAYS``）
  - ``x = side_days``（两侧异类极值跨度；缺侧回退规则同前）
  - 组内相对线性：跨度越大越高分，``t ∈ [0, 1]`` 后 × ``W_DAYS``
- **两侧差距**（可超过 ``W_GAP``）
  - 取左右相对涨跌幅中绝对值较大者 × ``W_GAP``
  - 谷：``(峰 − 谷) / 峰``；峰：``(峰 − 谷) / 谷``

``score = score_price + score_days + score_gap``。
"""

from __future__ import annotations

from typing import Any

# 三维权重（价格 / 天数先组内归一到 [0,1] 再乘权重）
W_PRICE = 30.0
W_DAYS = 30.0
W_GAP = 40.0


def _flanking(
    seq: list[dict[str, Any]],
    i: int,
    want_type: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    left: dict[str, Any] | None = None
    for j in range(i - 1, -1, -1):
        if seq[j].get("type") == want_type:
            left = seq[j]
            break
    right: dict[str, Any] | None = None
    for j in range(i + 1, len(seq)):
        if seq[j].get("type") == want_type:
            right = seq[j]
            break
    return left, right


def _side_days(
    point: dict[str, Any],
    left: dict[str, Any] | None,
    right: dict[str, Any] | None,
) -> int:
    idx = int(point.get("index", 0))
    if left is not None and right is not None:
        return max(0, int(right["index"]) - int(left["index"]))
    if left is not None:
        return max(0, idx - int(left["index"]))
    if right is not None:
        return max(0, int(right["index"]) - idx)
    return int(point.get("span_days") or 0)


def _rel_gap(high: float, low: float, *, denom: float) -> float:
    """相对差距 (high − low) / |denom|。"""
    d = abs(denom)
    if d <= 0:
        return 0.0
    return max(0.0, (high - low) / d)


def _gap_vs_flanks(
    point: dict[str, Any],
    left: dict[str, Any] | None,
    right: dict[str, Any] | None,
    *,
    kind: str,
) -> tuple[float | None, float | None, float, float]:
    """返回 (left_gap, right_gap, gap_mean, gap_max)。相对比例。

    - 谷：相对左右峰 ``(峰 − 谷) / 峰``
    - 峰：相对左右谷 ``(峰 − 谷) / 谷``
    """
    price = float(point["price"])
    left_gap: float | None = None
    right_gap: float | None = None
    parts: list[float] = []

    if kind == "trough":
        if left is not None:
            lp = float(left["price"])
            left_gap = round(_rel_gap(lp, price, denom=lp), 6)
            parts.append(left_gap)
        if right is not None:
            rp = float(right["price"])
            right_gap = round(_rel_gap(rp, price, denom=rp), 6)
            parts.append(right_gap)
    else:
        if left is not None:
            lp = float(left["price"])
            left_gap = round(_rel_gap(price, lp, denom=lp), 6)
            parts.append(left_gap)
        if right is not None:
            rp = float(right["price"])
            right_gap = round(_rel_gap(price, rp, denom=rp), 6)
            parts.append(right_gap)

    gap_mean = sum(parts) / len(parts) if parts else 0.0
    gap_max = max((abs(v) for v in parts), default=0.0)
    return left_gap, right_gap, gap_mean, gap_max


def _competition_ranks(values: list[float], *, higher_better: bool) -> list[int]:
    """竞争名次：严格更优的个数 + 1。"""
    ranks: list[int] = []
    for i, p in enumerate(values):
        if higher_better:
            better = sum(1 for j, q in enumerate(values) if j != i and q > p)
        else:
            better = sum(1 for j, q in enumerate(values) if j != i and q < p)
        ranks.append(better + 1)
    return ranks


def _linear_norm(values: list[float], *, higher_better: bool) -> list[float]:
    """组内线性归一到 [0, 1]。全相同则全为 1。"""
    if not values:
        return []
    lo = min(values)
    hi = max(values)
    if hi <= lo:
        return [1.0] * len(values)
    span = hi - lo
    if higher_better:
        return [(v - lo) / span for v in values]
    return [(hi - v) / span for v in values]


def _score_gap_from_max(gap_max: float) -> float:
    return abs(float(gap_max)) * W_GAP


def _score_group(
    seq: list[dict[str, Any]],
    indices: list[int],
    *,
    kind: str,
) -> list[dict[str, Any]]:
    """对同类型下标列表打分。``kind`` 为 peak / trough。"""
    if not indices:
        return []

    flank_type = "trough" if kind == "peak" else "peak"
    prices: list[float] = []
    meta: list[dict[str, Any]] = []

    for i in indices:
        pt = seq[i]
        left, right = _flanking(seq, i, flank_type)
        side_days = _side_days(pt, left, right)
        left_gap, right_gap, gap_mean, gap_max = _gap_vs_flanks(
            pt, left, right, kind=kind
        )
        prices.append(float(pt["price"]))
        meta.append(
            {
                "left": left,
                "right": right,
                "side_days": side_days,
                "left_gap": left_gap,
                "right_gap": right_gap,
                "gap_mean": gap_mean,
                "gap_max": gap_max,
            }
        )

    days = [float(m["side_days"]) for m in meta]
    price_t = _linear_norm(prices, higher_better=(kind == "peak"))
    days_t = _linear_norm(days, higher_better=True)
    ranks = _competition_ranks(prices, higher_better=(kind == "peak"))

    out: list[dict[str, Any]] = []
    for k, i in enumerate(indices):
        pt = seq[i]
        m = meta[k]
        rank = ranks[k]
        sp = price_t[k] * W_PRICE
        sd = days_t[k] * W_DAYS
        sg = _score_gap_from_max(m["gap_max"])
        total = sp + sd + sg
        row = {
            "type": kind,
            "label": "波峰" if kind == "peak" else "波谷",
            "date": pt.get("date"),
            "index": pt.get("index"),
            "price": pt.get("price"),
            "span_days": pt.get("span_days"),
            "side_days": m["side_days"],
            "left_gap": m["left_gap"],
            "right_gap": m["right_gap"],
            "gap_mean": round(m["gap_mean"], 6),
            "gap_max": round(m["gap_max"], 6),
            "price_rank": rank,
            "left_date": (m["left"] or {}).get("date") if m["left"] else None,
            "right_date": (m["right"] or {}).get("date") if m["right"] else None,
            "score_price": round(sp, 4),
            "score_days": round(sd, 4),
            "score_gap": round(sg, 4),
            "score": round(total, 2),
        }
        out.append(row)

    out.sort(key=lambda r: (-float(r["score"]), int(r.get("index") or 0)))
    return out


def score_extrema(seq: list[dict[str, Any]]) -> dict[str, Any]:
    """对峰谷序列评分，返回 ``peak_scores`` / ``trough_scores`` 两条序列。"""
    peak_idx = [i for i, p in enumerate(seq) if p.get("type") == "peak"]
    trough_idx = [i for i, p in enumerate(seq) if p.get("type") == "trough"]
    peak_scores = _score_group(seq, peak_idx, kind="peak")
    trough_scores = _score_group(seq, trough_idx, kind="trough")
    return {
        "peak_scores": peak_scores,
        "trough_scores": trough_scores,
        "score_weights": {
            "price": W_PRICE,
            "days": W_DAYS,
            "gap": W_GAP,
        },
    }
