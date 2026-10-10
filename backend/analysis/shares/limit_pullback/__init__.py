"""涨停回踩筛选：N天内有涨停 + 现价贴近窗口最低点 / 涨停开盘价。"""
from __future__ import annotations

import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from analysis.decline.bars import parse_bars
from analysis.shares.common.candidates import collect_universe
from analysis.shares.common.config import KLINE_LIMIT
from analysis.shares.common.view import apply_view
from company.line.fetcher import fetch_kline
from core.fmt import to_float

logger = logging.getLogger(__name__)


def limit_threshold(code: str, name: str = "") -> float:
    c = str(code or "").strip()
    if c.startswith(("300", "688")):
        return 19.2
    if c.startswith(("92", "43", "87", "88")):
        return 28.5
    if "ST" in str(name or "").upper() or "*ST" in str(name or ""):
        return 4.8
    return 9.2


def normalize_params(raw: dict[str, Any] | None) -> dict[str, Any]:
    src = raw if isinstance(raw, dict) else {}
    window = int(to_float(src.get("window")) or 15)
    window = max(5, min(30, window))
    def _pct(v, d):
        n = to_float(v)
        return float(n) if n is not None and n >= 0 else d
    mode = str(src.get("mode") or "either").lower()
    if mode not in ("low", "open", "either", "both"):
        mode = "either"
    return {
        "window": window,
        "limit_up_min": max(1, int(to_float(src.get("limit_up_min")) or 1)),
        "dist_low_max": _pct(src.get("dist_low_max"), 5.0),
        "dist_open_max": _pct(src.get("dist_open_max"), 5.0),
        "mode": mode,
        "days_since_limit_max": int(to_float(src.get("days_since_limit_max")) or window),
        "touch_only": bool(src.get("touch_only", False)),
        "exclude_st": bool(src.get("exclude_st", True)),
    }


def fingerprint(params: dict[str, Any]) -> str:
    text = json.dumps(params, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "lpb_" + hashlib.sha1(text.encode()).hexdigest()[:16]


def match_pullback(bars: list[dict], code: str = "", name: str = "", params: dict | None = None) -> dict | None:
    p = normalize_params(params)
    w = p["window"]
    if len(bars) < 2:
        return None
    win = bars[-w:] if len(bars) >= w else list(bars)
    th = limit_threshold(code, name)
    # 涨停下标（相对win）
    ups: list[int] = []
    for i, b in enumerate(win):
        prev = win[i - 1].get("close") if i > 0 else (bars[len(bars) - len(win) + i - 1].get("close") if len(bars) > len(win) else None)
        prev = to_float(prev)
        close = to_float(b.get("close"))
        high = to_float(b.get("high"))
        if prev and prev > 0 and close:
            pct = (close / prev - 1) * 100
            touch = ((high or close) / prev - 1) * 100
            hit = touch >= th - 0.5 if p["touch_only"] else pct >= th - 0.8
            # ST 用更严
            if hit:
                ups.append(i)
    if len(ups) < p["limit_up_min"]:
        return None
    last = ups[-1]
    days_since = len(win) - 1 - last
    if days_since > p["days_since_limit_max"]:
        return None
    lows = [to_float(b.get("low")) for b in win]
    lows = [v for v in lows if v and v > 0]
    if not lows:
        return None
    low_n = min(lows)
    c0 = to_float(win[-1].get("close"))
    o_star = to_float(win[last].get("open"))
    if not c0 or not o_star:
        return None
    dist_low = (c0 - low_n) / low_n * 100
    dist_open = (c0 - o_star) / o_star * 100
    hit_low = dist_low <= p["dist_low_max"]
    hit_open = abs(dist_open) <= p["dist_open_max"]
    mode = p["mode"]
    ok = (hit_low or hit_open) if mode == "either" else (hit_low and hit_open) if mode == "both" else (hit_low if mode == "low" else hit_open)
    if not ok:
        return None
    hi_after = max([to_float(b.get("high")) or 0 for b in win[last:]] or [c0])
    drawdown = (c0 / hi_after - 1) * 100 if hi_after else 0
    score = 25.0 if (hit_low and hit_open) else 15.0
    score += max(0, 15 - days_since)
    score += min(15, len(ups) * 5)
    score -= max(0, dist_low) * 1.5 + abs(dist_open) * 1.0
    score = round(score, 2)
    return {
        "as_of": str(win[-1].get("date") or ""),
        "limit_dates": [str(win[i].get("date")) for i in ups],
        "limit_count": len(ups),
        "last_limit_date": str(win[last].get("date")),
        "days_since_limit": days_since,
        "low_n": round(low_n, 4),
        "open_star": round(o_star, 4),
        "close_now": round(c0, 4),
        "dist_low": round(dist_low, 2),
        "dist_open": round(dist_open, 2),
        "hit_low": hit_low,
        "hit_open": hit_open,
        "drawdown": round(drawdown, 2),
        "score": score,
    }


def analyze_one(meta: dict, params: dict) -> dict | None:
    code = str(meta.get("code") or "").strip()
    if not code:
        return None
    name0 = str(meta.get("name") or "")
    if params.get("exclude_st") and ("ST" in name0.upper()):
        return None
    try:
        pack = fetch_kline(code, period="day", adjust="qfq", limit=KLINE_LIMIT)
    except Exception as exc:
        logger.info("kline failed %s: %s", code, exc)
        return None
    bars = parse_bars(list(pack.get("items") or []))
    if not bars:
        return None
    name = str(meta.get("name") or pack.get("name") or "")
    if params.get("exclude_st") and ("ST" in name.upper()):
        return None
    hit = match_pullback(bars, code=code, name=name, params=params)
    if not hit:
        return None
    return {
        "code": code, "name": name,
        "l1_name": meta.get("l1_name") or "", "l2_name": meta.get("l2_name") or "", "l3_name": meta.get("l3_name") or "",
        **hit,
        "matched_days": hit["limit_count"],
        "kline_source": pack.get("source"), "kline_count": len(bars),
    }


def screen_pullback(params: dict | None = None, code: str = "", workers: int = 8, top: int | None = None,
                    on_update: Callable | None = None) -> dict:
    p = normalize_params(params)
    pool = collect_universe(code)
    cands = list(pool.get("candidates") or [])
    results: list[dict] = []
    tick = 0
    def _assemble(rows, analyzed):
        items = sorted(rows, key=lambda r: (-float(r.get("score") or 0), str(r.get("code") or "")))
        for i, r in enumerate(items, 1):
            r["rank"] = i
        as_of = items[0].get("as_of", "") if items else ""
        return {"updated_at": as_of, "fingerprint": fingerprint(p), "params": p,
                "candidate_count": len(cands), "analyzed_count": analyzed,
                "result_count": len(items), "items": items, "errors": [],
                "note": f"窗口{p['window']}天内≥{p['limit_up_min']}涨停；贴最低≤{p['dist_low_max']}% / 贴涨停开盘±{p['dist_open_max']}%（{p['mode']}）"}
    if not cands:
        return apply_view(_assemble([], 0), top)
    mw = min(max(1, workers), len(cands))
    with ThreadPoolExecutor(max_workers=mw) as ex:
        futs = {ex.submit(analyze_one, m, p): m for m in cands}
        for fut in as_completed(futs):
            try:
                row = fut.result()
            except Exception:
                row = None
            tick += 1
            if row:
                results.append(row)
            if on_update and (tick <= 8 or tick % 40 == 0 or tick == len(cands)):
                on_update(_assemble(list(results), tick))
    return apply_view(_assemble(results, len(cands)), top)
