"""个股分析耗时剖析（优先读本地 K 线缓存，可离线跑）。

用法（在 backend 目录）::

    python -m analysis.evaluate.bench_speed
    python -m analysis.evaluate.bench_speed --codes 600519,000001,000002 --limit 30
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from core.paths import KLINE_CACHE_DIR

from company.analysis.line.evaluate.core import find_max_range, score_low_point, lowest_day
from company.analysis.line.evaluate.service import (
    EXTREMA_LOOKBACK_BARS,
    EXTREMA_LOOKBACK_DAYS,
    _ensure_extrema_history,
    _extrema_bars,
    _safe_divergence,
    _safe_paths,
    analyze_evaluate,
)
from company.analysis.line.undulate.service import _bar_date, _fetch_day_range, _today_iso
from company.analysis.line.undulate.volatility import _fetch_index_day_range, _norm_index_code


def _load_disk_bars(code: str, *, adjust: str = "qfq") -> list[dict[str, Any]]:
    path = KLINE_CACHE_DIR / f"{code}_day_{adjust}.json"
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    items = list(raw.get("items") or [])
    items.sort(key=_bar_date)
    return items


def _slice_lookback(bars: list[dict[str, Any]], *, end: str, days: int) -> list[dict[str, Any]]:
    beg = (
        datetime.strptime(end, "%Y-%m-%d") - timedelta(days=int(days))
    ).strftime("%Y-%m-%d")
    return [b for b in bars if beg <= _bar_date(b) <= end]


def _slice_last_bars(
    bars: list[dict[str, Any]], *, end: str, n: int = EXTREMA_LOOKBACK_BARS
) -> list[dict[str, Any]]:
    ordered = [b for b in bars if (d := _bar_date(b)) and d <= end]
    ordered.sort(key=_bar_date)
    return ordered[-int(n) :] if len(ordered) > int(n) else ordered


def _timed(fn, *args, **kwargs) -> tuple[Any, float]:
    t0 = time.perf_counter()
    out = fn(*args, **kwargs)
    return out, time.perf_counter() - t0


def _pick_codes(limit: int, explicit: str) -> list[str]:
    if explicit.strip():
        return [c.strip() for c in explicit.split(",") if c.strip()]
    files = sorted(KLINE_CACHE_DIR.glob("*_day_qfq.json"))
    codes: list[str] = []
    for path in files:
        name = path.name
        if name.startswith(("sh", "sz", "bj")):
            continue
        code = name.split("_", 1)[0]
        if len(code) == 6 and code.isdigit():
            # 跳过创业板 / 科创板，贴近 screen 宇宙
            if code.startswith(("300", "301", "688", "689")):
                continue
            codes.append(code)
        if len(codes) >= limit:
            break
    return codes


def profile_one(
    code: str,
    *,
    band: float,
    factor: str,
    lookback: int,
    index_hist: dict[str, Any] | None,
    end: str,
) -> dict[str, Any]:
    full = _load_disk_bars(code)
    if len(full) < 30:
        # 磁盘没有则走 fetcher（可能打网）
        beg = (
            datetime.strptime(end, "%Y-%m-%d") - timedelta(days=lookback)
        ).strftime("%Y-%m-%d")
        t0 = time.perf_counter()
        hist = _fetch_day_range(code, beg_iso=beg, end_iso=end, adjust="qfq")
        fetch_s = time.perf_counter() - t0
        bars = list(hist.get("items") or [])
        source = f"fetch:{hist.get('source') or ''}"
    else:
        t0 = time.perf_counter()
        bars = _slice_lookback(full, end=end, days=lookback)
        fetch_s = time.perf_counter() - t0
        source = "disk"

    if len(bars) < 5:
        return {"code": code, "error": "bars<5", "source": source}

    result, find_s = _timed(find_max_range, bars, end=end, factor=factor, band=band)
    row: dict[str, Any] = {
        "code": code,
        "source": source,
        "bars": len(bars),
        "fetch_s": round(fetch_s, 4),
        "find_s": round(find_s, 4),
        "tested": result.get("tested"),
        "found": bool(result.get("found")),
        "reached_start": bool(result.get("reached_start")),
    }
    if not result.get("found"):
        row["total_s"] = round(fetch_s + find_s, 4)
        return row

    window = result["window"]
    beg = window["beg"]
    used_end = window["end"]
    row["window_days"] = window.get("count")

    # 补最近 900 交易日
    t0 = time.perf_counter()
    if source == "disk":
        bars_ext = _slice_last_bars(full, end=used_end, n=EXTREMA_LOOKBACK_BARS)
        hist = {"items": bars_ext, "name": code, "source": "disk"}
    else:
        bars_ext, hist = _ensure_extrema_history(
            code, bars, {"items": bars, "name": code, "source": source},
            end_iso=used_end, adjust="qfq",
        )
    extrema_fetch_s = time.perf_counter() - t0

    low = lowest_day(window, factor=factor)
    extrema_bars = _extrema_bars(bars_ext, end=used_end)
    score_s = 0.0
    if low is not None and extrema_bars:
        _, score_s = _timed(
            score_low_point,
            extrema_bars,
            low["date"],
            series=factor,
            layers=3,
            smooth_window=1,
            match_beg=beg,
            match_end=used_end,
        )

    paths, paths_s = _timed(
        _safe_paths,
        bars5,
        "000001",
        beg=beg,
        end=used_end,
        stock_code=code,
        stock_name=str(hist.get("name") or ""),
        index_hist=index_hist,
    )
    div, div_s = _timed(
        _safe_divergence,
        code,
        "000001",
        beg=beg,
        end=used_end,
        factor=factor,
        stock_bars=bars5,
        stock_name=str(hist.get("name") or ""),
        stock_source=str(hist.get("source") or ""),
        index_hist=index_hist,
    )

    total = fetch_s + find_s + extrema_fetch_s + score_s + paths_s + div_s
    row.update(
        {
            "extrema_fetch_s": round(extrema_fetch_s, 4),
            "score_s": round(score_s, 4),
            "paths_s": round(paths_s, 4),
            "div_s": round(div_s, 4),
            "div_score": (div or {}).get("score"),
            "paths_err": (paths or {}).get("error"),
            "total_s": round(total, 4),
        }
    )
    return row


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    keys = [
        "fetch_s",
        "find_s",
        "extrema_fetch_s",
        "score_s",
        "paths_s",
        "div_s",
        "total_s",
    ]
    found = [r for r in rows if r.get("found")]
    missed = [r for r in rows if r.get("found") is False]
    out: dict[str, Any] = {
        "n": len(rows),
        "found": len(found),
        "missed": len(missed),
        "errors": sum(1 for r in rows if r.get("error")),
    }
    for key in keys:
        vals = [float(r[key]) for r in rows if key in r]
        if not vals:
            continue
        out[f"{key}_sum"] = round(sum(vals), 4)
        out[f"{key}_avg"] = round(sum(vals) / len(vals), 4)
        out[f"{key}_max"] = round(max(vals), 4)
    if found:
        tested = [int(r.get("tested") or 0) for r in found]
        out["tested_avg_found"] = round(sum(tested) / len(tested), 1)
        out["tested_max_found"] = max(tested)
    if missed:
        tested = [int(r.get("tested") or 0) for r in missed]
        out["tested_avg_miss"] = round(sum(tested) / len(tested), 1)
    return out


def bench_find_max_range_algo(codes: list[str], *, end: str, band: float, lookback: int) -> None:
    """对比旧实现（当前）在不同窗口长度下的耗时分布。"""
    print("\n=== find_max_range 耗时 vs tested 窗口数 ===")
    samples: list[tuple[int, float, bool]] = []
    for code in codes:
        bars = _load_disk_bars(code)
        if len(bars) < 30:
            continue
        bars = _slice_lookback(bars, end=end, days=lookback)
        result, dt = _timed(find_max_range, bars, end=end, factor="close", band=band)
        tested = int(result.get("tested") or 0)
        samples.append((tested, dt, bool(result.get("found"))))
        if len(samples) >= 40:
            break
    if not samples:
        print("无样本")
        return
    samples.sort(key=lambda x: x[0])
    for tested, dt, found in samples[:: max(1, len(samples) // 8)]:
        print(f"  tested={tested:4d}  find_s={dt:.4f}  found={found}")
    # 相关性粗看：tested 最大的几只
    top = sorted(samples, key=lambda x: x[1], reverse=True)[:5]
    print("  最慢 5 次:")
    for tested, dt, found in top:
        print(f"    tested={tested:4d}  find_s={dt:.4f}  found={found}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--codes", default="", help="逗号分隔代码；空则从缓存挑")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--band", type=float, default=0.09)
    ap.add_argument("--factor", default="close")
    ap.add_argument("--lookback", type=int, default=900)
    ap.add_argument("--end", default="")
    ap.add_argument("--full-analyze", type=int, default=5, help="再跑 N 次完整 analyze_evaluate")
    args = ap.parse_args()

    end = args.end or _today_iso()
    codes = _pick_codes(args.limit, args.codes)
    print(f"codes={len(codes)} end={end} band={args.band} lookback={args.lookback}")
    print(f"kline_cache={KLINE_CACHE_DIR} exists={Path(KLINE_CACHE_DIR).exists()}")

    # 预取指数
    index_hist = None
    try:
        beg = (
            datetime.strptime(end, "%Y-%m-%d") - timedelta(days=3650)
        ).strftime("%Y-%m-%d")
        index_hist, idx_s = _timed(
            _fetch_index_day_range,
            _norm_index_code("000001") or "000001",
            beg_iso=beg,
            end_iso=end,
        )
        print(f"index_prefetch_s={idx_s:.4f} bars={len(index_hist.get('items') or [])}")
    except Exception as exc:  # noqa: BLE001
        print(f"index_prefetch_failed: {exc}")

    rows: list[dict[str, Any]] = []
    t0 = time.perf_counter()
    for code in codes:
        rows.append(
            profile_one(
                code,
                band=args.band,
                factor=args.factor,
                lookback=args.lookback,
                index_hist=index_hist,
                end=end,
            )
        )
    wall = time.perf_counter() - t0
    summary = summarize(rows)
    print("\n=== 分阶段汇总（串行）===")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print(f"  wall_s: {wall:.4f}")

    slow = sorted(
        [r for r in rows if "total_s" in r],
        key=lambda r: r["total_s"],
        reverse=True,
    )[:8]
    print("\n=== 最慢样本 ===")
    for r in slow:
        print(
            f"  {r['code']} total={r.get('total_s')} find={r.get('find_s')} "
            f"tested={r.get('tested')} found={r.get('found')} "
            f"score={r.get('score_s')} paths={r.get('paths_s')} div={r.get('div_s')}"
        )

    bench_find_max_range_algo(codes, end=end, band=args.band, lookback=args.lookback)

    if args.full_analyze > 0 and codes:
        print("\n=== 完整 analyze_evaluate ===")
        for code in codes[: args.full_analyze]:
            try:
                out, dt = _timed(
                    analyze_evaluate,
                    code,
                    end=end,
                    band=args.band,
                    factor=args.factor,
                    lookback_days=args.lookback,
                    index_hist=index_hist,
                )
                print(
                    f"  {code}: {dt:.4f}s found={out.get('found')} "
                    f"tested={out.get('tested')}"
                )
            except Exception as exc:  # noqa: BLE001
                print(f"  {code}: ERROR {exc}")


if __name__ == "__main__":
    main()
