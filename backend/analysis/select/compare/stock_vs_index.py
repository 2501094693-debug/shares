"""股票 vs 指数 OHLC 四图偏离方案.

X=日期, Y=DIF 原值, 方向四类, 每图一分 + 一总分.

数据源全部复用系统已有功能:
- 个股与指数统一用 company.line.eastmoney.kline.fetch_line
  (指数如 SH000001 走同接口, resolve_secid 已支持).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from company.line.eastmoney.kline import fetch_line

FACTORS = ("open", "high", "low", "close")
WEIGHTS = {"open": 0.15, "high": 0.20, "low": 0.25, "close": 0.40}
REVERSE_WEIGHT = 1.5
FLAT_EPS = 0.0003


def _norm_date(v: str) -> str:
    return str(v or "")[:10].replace("/", "-")


def _factors_of(bars: list[dict[str, Any]]) -> dict[str, dict[str, float | None]]:
    """每根算 r_open/r_high/r_low/r_close, 相对各自前收."""
    out: dict[str, dict[str, float | None]] = {}
    for i, b in enumerate(bars):
        date = _norm_date(str(b.get("time") or ""))
        if not date:
            continue
        if i == 0:
            prev = b.get("close")
            # 首根无前收则跳过
            if prev is None:
                continue
            # 用首根自身无法算环比, 记 None 由对齐层丢弃
            out[date] = {f: None for f in FACTORS}
            continue
        prev = bars[i - 1].get("close")
        if not prev:
            out[date] = {f: None for f in FACTORS}
            continue
        row: dict[str, float | None] = {}
        for f in FACTORS:
            v = b.get(f)
            row[f] = (float(v) / float(prev) - 1.0) if v is not None else None
        out[date] = row
    return out


def classify_dir(rs: float, rb: float) -> str:
    s = 1 if rs > FLAT_EPS else (-1 if rs < -FLAT_EPS else 0)
    b = 1 if rb > FLAT_EPS else (-1 if rb < -FLAT_EPS else 0)
    if s == 1 and b == 1:
        return "同涨"
    if s == -1 and b == -1:
        return "同跌"
    if s >= 0 and b <= 0 and s != b:
        return "股涨指跌"
    return "股跌指涨"


_FETCH_RETRIES = 3


def _fetch_with_retry(code: str, **kwargs: object) -> dict[str, Any]:
    """Eastmoney偶发RemoteDisconnected, 最多重试3次, 仍失败抛友好ValueError。"""
    import time as _time

    last_exc: Exception | None = None
    for attempt in range(_FETCH_RETRIES):
        try:
            return fetch_line(code, **kwargs)  # type: ignore[arg-type]
        except ValueError:
            raise
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            _time.sleep(1.0 + attempt)
    raise ValueError(f"行情接口暂时抖动({code})，请稍后重试")


def compare_stock_vs_index(stock: str, index: str, beg: str, end: str) -> dict[str, Any]:
    """主入口: 返回每日 DIF+方向、每图一分、汇总总分."""
    s_pack = _fetch_with_retry(stock, period="day", adjust="qfq", beg=beg, end=end)
    b_pack = _fetch_with_retry(index, period="day", adjust="none", beg=beg, end=end)
    s_fac = _factors_of(list(s_pack.get("items") or []))
    b_fac = _factors_of(list(b_pack.get("items") or []))
    dates = sorted(d for d in s_fac if d in b_fac)

    daily: dict[str, list[dict[str, Any]]] = {f: [] for f in FACTORS}
    for d in dates:
        for f in FACTORS:
            rs, rb = s_fac[d][f], b_fac[d][f]
            if rs is None or rb is None:
                continue
            dif = float(rs) - float(rb)
            daily[f].append({"date": d, "rs": round(rs, 6), "rb": round(rb, 6),
                             "dif": round(dif, 6), "dir": classify_dir(rs, rb)})

    scores: dict[str, float] = {}
    for f in FACTORS:
        rows = daily[f]
        if not rows:
            scores[f] = 0.0
            continue
        tot = 0.0
        for r in rows:
            w = 1.0 if r["dir"] in ("同涨", "同跌") else REVERSE_WEIGHT
            tot += abs(r["dif"]) * w
        scores[f] = round(tot / len(rows) * 100, 4)

    total = round(sum(scores[f] * WEIGHTS[f] for f in FACTORS), 4)
    if total < 0.5:
        level = "紧贴"
    elif total < 1.0:
        level = "轻度偏离"
    elif total < 2.0:
        level = "明显偏离"
    else:
        level = "极端偏离"
    contrib = sorted(FACTORS, key=lambda f: scores[f] * WEIGHTS[f], reverse=True)
    return {"meta": {"stock": stock, "index": index, "beg": beg, "end": end, "n": len(dates),
                     "stock_name": s_pack.get("name"), "index_name": b_pack.get("name")},
            "dates": dates, "daily": daily, "scores": scores,
            "total": {"value": total, "level": level, "top": contrib[:2]}}
