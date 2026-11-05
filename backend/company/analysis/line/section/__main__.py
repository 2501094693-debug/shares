"""CLI：把个股区间日线划分为涨 / 跌 / 横盘段。

示例::

    python -m company.analysis.line.section 600519 --beg 2026-01-01
    python -m company.analysis.line.section 600519 --beg 20260101 --end 20260301
    python -m company.analysis.line.section 600519 --beg 20260101 --band 0.03 --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[4]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from company.analysis.line.section.service import analyze_sections


def _fmt_pct(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v:+.2f}%"


def _print_segments(segments: list[dict], depth: int = 0) -> None:
    pad = "  " * depth
    for seg in segments:
        flag = seg.get("flag") or seg.get("direction")
        line = (
            f"{pad}{seg.get('begin')} → {seg.get('end')}  "
            f"{flag}  {_fmt_pct(seg.get('change_pct'))}  "
            f"({seg.get('change_price'):+g})  L{seg.get('level')}"
        )
        if seg.get("amplitude_pct") is not None:
            line += f"  振幅 {seg['amplitude_pct']:.2f}%"
        print(line)
        children = seg.get("children") or []
        if children and depth < 1:
            _print_segments(children, depth + 1)


def _print_text(pack: dict) -> None:
    print(
        f"{pack.get('code')} {pack.get('name') or ''}  "
        f"[{pack.get('beg')} → {pack.get('end')}]  "
        f"共 {pack.get('count')} 个交易日  "
        f"最小段 {pack.get('minimal_count')} / 同向段 {pack.get('run_count')} / "
        f"最终段 {pack.get('segment_count')}"
    )
    _print_segments(pack.get("segments") or [])


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="日线段划分：最小段 → 同向段 → 涨/跌/横盘")
    p.add_argument("code", nargs="?", help="股票代码，如 600519")
    p.add_argument("--beg", default="", help="起始日期 YYYY-MM-DD 或 YYYYMMDD")
    p.add_argument("--end", default="", help="结束日期，默认今天")
    p.add_argument("--series", default="close", help="open/close/high/low/ohlc4")
    p.add_argument("--band", type=float, default=0.09, help="横盘带宽阈值，默认 0.09")
    p.add_argument("--min-runs", type=int, default=2, help="横盘最少交替段数，默认 2")
    p.add_argument("--adjust", default="qfq", help="qfq/hfq/none，默认前复权")
    p.add_argument("--json", action="store_true", help="输出完整 JSON")
    args = p.parse_args(argv)

    if not args.code or not args.beg:
        p.error("须提供 code 与 --beg")

    try:
        pack = analyze_sections(
            args.code,
            args.beg,
            args.end,
            series=args.series,
            band_pct=args.band,
            min_runs=args.min_runs,
            adjust=args.adjust,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(pack, ensure_ascii=False, indent=2))
    else:
        _print_text(pack)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
