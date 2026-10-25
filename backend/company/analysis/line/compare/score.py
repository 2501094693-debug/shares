"""方向分类与相对强弱 / 偏离汇总。

默认：波动标准化（选区闭区间）
  在对比区间 [beg, end] 内，按因子分别算股/指涨跌幅的样本标准差 σ
  zs = rs / σ_s ， zb = rb / σ_b ， zdif = zs − zb
  强弱 score = (Σ zdif × 权重) / n
  偏离 score = (Σ |zdif| × 权重) / n

回退（σ 不足，区间有效日 < 2 或 σ≈0）：
  强弱/偏离仍用裸 dif，并 ×100（百分点量级）
"""

from __future__ import annotations

import math
from typing import Any

from company.analysis.line.compare.codes import FACTORS

FLAT_EPS = 0.0003  # 约 0.03% 内视为平
REVERSE_WEIGHT = 1.5
WEIGHTS = {"open": 0.15, "high": 0.20, "low": 0.25, "close": 0.40}

# 闭区间样本标准差至少需要 2 个点
VOL_MIN_PERIODS = 2
SIGMA_FLOOR = 1e-5

DIR_SAME_UP = "同涨"
DIR_SAME_DOWN = "同跌"
DIR_STOCK_UP_INDEX_DOWN = "股涨指跌"
DIR_STOCK_DOWN_INDEX_UP = "股跌指涨"


def classify_dir(rs: float, rb: float, *, eps: float = FLAT_EPS) -> str:
    """按股/指涨跌幅符号分类四向关系。"""
    s = 1 if rs > eps else (-1 if rs < -eps else 0)
    b = 1 if rb > eps else (-1 if rb < -eps else 0)
    if s == 1 and b == 1:
        return DIR_SAME_UP
    if s == -1 and b == -1:
        return DIR_SAME_DOWN
    if s >= 0 and b <= 0 and s != b:
        return DIR_STOCK_UP_INDEX_DOWN
    return DIR_STOCK_DOWN_INDEX_UP


def _sample_std(values: list[float]) -> float | None:
    n = len(values)
    if n < 2:
        return None
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    if var <= 0:
        return None
    return math.sqrt(var)


def range_sigma(
    fac: dict[str, dict[str, float | None]],
    factor: str,
    dates: list[str],
    *,
    min_periods: int = VOL_MIN_PERIODS,
    sigma_floor: float = SIGMA_FLOOR,
) -> float | None:
    """用 dates 闭区间内该因子全部有效涨跌幅，算一个样本标准差。"""
    values: list[float] = []
    for d in dates:
        val = (fac.get(d) or {}).get(factor)
        if val is None:
            continue
        values.append(float(val))
    if len(values) < min_periods:
        return None
    sig = _sample_std(values)
    if sig is None or sig < sigma_floor:
        return None
    return sig


def pair_row(
    rs: float,
    rb: float,
    *,
    sigma_s: float | None = None,
    sigma_b: float | None = None,
    sigma_floor: float = SIGMA_FLOOR,
) -> dict[str, Any]:
    dif = float(rs) - float(rb)
    row: dict[str, Any] = {
        "rs": round(rs, 6),
        "rb": round(rb, 6),
        "dif": round(dif, 6),
        "dir": classify_dir(rs, rb),
        "norm": "raw",
        "zdif": None,
        "zs": None,
        "zb": None,
        "sigma_s": None,
        "sigma_b": None,
    }
    if (
        sigma_s is not None
        and sigma_b is not None
        and float(sigma_s) >= sigma_floor
        and float(sigma_b) >= sigma_floor
    ):
        zs = float(rs) / float(sigma_s)
        zb = float(rb) / float(sigma_b)
        row["zs"] = round(zs, 6)
        row["zb"] = round(zb, 6)
        row["sigma_s"] = round(float(sigma_s), 6)
        row["sigma_b"] = round(float(sigma_b), 6)
        row["zdif"] = round(zs - zb, 6)
        row["norm"] = "vol"
    return row


def _dir_weight(dir_label: str) -> float:
    return 1.0 if dir_label in (DIR_SAME_UP, DIR_SAME_DOWN) else REVERSE_WEIGHT


def strength_level(total: float, *, mode: str = "vol") -> str:
    if mode == "vol":
        hi = (1.0, 0.5, 0.25)
    else:
        hi = (2.0, 1.0, 0.5)
    a, b, c = hi
    if total >= a:
        return "极端偏强"
    if total >= b:
        return "明显偏强"
    if total >= c:
        return "轻度偏强"
    if total > -c:
        return "持平"
    if total > -b:
        return "轻度偏弱"
    if total > -a:
        return "明显偏弱"
    return "极端偏弱"


def deviation_level(mag: float, *, mode: str = "vol") -> str:
    if mode == "vol":
        cuts = (0.25, 0.5, 1.0)
    else:
        cuts = (0.5, 1.0, 2.0)
    if mag < cuts[0]:
        return "紧贴"
    if mag < cuts[1]:
        return "轻度偏离"
    if mag < cuts[2]:
        return "明显偏离"
    return "极端偏离"


def summarize_factor(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """单因子强弱分、偏离分 + 方向计数。

    优先用 zdif（波动标准化，sigma 单位）；不足则回退裸 dif×100。
    """
    counts = {
        DIR_SAME_UP: 0,
        DIR_SAME_DOWN: 0,
        DIR_STOCK_UP_INDEX_DOWN: 0,
        DIR_STOCK_DOWN_INDEX_UP: 0,
    }
    if not rows:
        return {
            "score": 0.0,
            "deviation": 0.0,
            "n": 0,
            "dirs": counts,
            "mode": "vol",
        }

    for row in rows:
        d = str(row.get("dir") or "")
        if d in counts:
            counts[d] += 1

    vol_rows = [r for r in rows if r.get("zdif") is not None]
    # 过半交易日有 zdif 即用波动口径（闭区间 σ 一旦算成，通常全日都有）
    use_vol = len(vol_rows) >= VOL_MIN_PERIODS and len(vol_rows) * 2 >= len(rows)
    if use_vol:
        use = vol_rows
        key = "zdif"
        scale = 1.0
        mode = "vol"
    else:
        use = rows
        key = "dif"
        scale = 100.0
        mode = "raw"

    tot = 0.0
    abs_tot = 0.0
    for row in use:
        w = _dir_weight(str(row.get("dir") or ""))
        dif = float(row[key]) * scale
        tot += dif * w
        abs_tot += abs(dif) * w
    n = len(use)
    score = round(tot / n, 4) if n else 0.0
    deviation = round(abs_tot / n, 4) if n else 0.0
    return {
        "score": score,
        "deviation": deviation,
        "n": n,
        "dirs": counts,
        "mode": mode,
    }


def summarize_all(daily: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    scores: dict[str, float] = {}
    deviations: dict[str, float] = {}
    dirs: dict[str, dict[str, int]] = {}
    modes: list[str] = []
    for f in FACTORS:
        pack = summarize_factor(daily.get(f) or [])
        scores[f] = float(pack["score"])
        deviations[f] = float(pack["deviation"])
        dirs[f] = dict(pack["dirs"])
        modes.append(str(pack.get("mode") or "raw"))

    mode = "vol" if modes.count("vol") >= modes.count("raw") else "raw"
    total = round(sum(scores[f] * WEIGHTS[f] for f in FACTORS), 4)
    dev_total = round(sum(deviations[f] * WEIGHTS[f] for f in FACTORS), 4)
    strength_top = sorted(
        FACTORS, key=lambda k: scores[k] * WEIGHTS[k], reverse=True
    )
    deviation_top = sorted(
        FACTORS, key=lambda k: deviations[k] * WEIGHTS[k], reverse=True
    )
    return {
        "scores": scores,
        "deviations": deviations,
        "dirs": dirs,
        "mode": mode,
        "total": {
            "value": total,
            "level": strength_level(total, mode=mode),
            "top": list(strength_top[:2]),
        },
        "deviation": {
            "value": dev_total,
            "level": deviation_level(dev_total, mode=mode),
            "top": list(deviation_top[:2]),
        },
        "norm": {
            "mode": mode,
            "scope": "range",
            "min_periods": VOL_MIN_PERIODS,
            "unit": "sigma" if mode == "vol" else "pct_point",
        },
    }
