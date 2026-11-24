"""CLI：MACD 股性（金叉日 + 后续 DIF≥DEA 段最大涨/跌幅）。

示例::

    python -m company.analysis.line.gene 600519 --beg 2024-01-02 --end 2024-12-31
    python -m company.analysis.line.gene 600519 --beg 20240102 --preset 12,26,9
    python -m company.analysis.line.gene 600519 --beg 2024-01-02 --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[4]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from company.analysis.line.gene.config import ALLOWED_PRESETS, DEFAULT_PRESET
from company.analysis.line.gene.service import analyze_gene


def _pct(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v * 100:.2f}%"


def _print_text(pack: dict) -> None:
    print(
        f"{pack.get('code')} {pack.get('name') or ''}  "
        f"[{pack.get('beg')} → {pack.get('end')}]  "
        f"MACD={pack.get('preset')}  "
        f"事件 {pack.get('event_count')} 条"
    )
    summary = pack.get("summary") or {}
    by_sig = summary.get("by_signal") or {}
    for sig, bucket in by_sig.items():
        n = int(bucket.get("count") or 0)
        if n <= 0:
            continue
        print(
            f"  {sig}: {n} 次  "
            f"均最大涨 {_pct(bucket.get('avg_max_close_gain'))}  "
            f"均最大跌 {_pct(bucket.get('avg_max_close_drop'))}"
        )
    events = list(pack.get("events") or [])
    if not events:
        print("  （区间内无金叉 / 即将金叉）")
        return
    for ev in events:
        if ev.get("judgment_failed"):
            span = (
                f"判断失败（{ev.get('decide_date') or ev.get('next_date') or '—'} "
                f"MACD={ev.get('decide_macd')} 低于信号日）"
            )
        elif ev.get("near_ok") is None and str(ev.get("signal") or "").startswith("即将"):
            span = "待验证（后续未翻正也未跌破信号日 MACD）"
        elif ev.get("dif_above_found"):
            open_mark = "…" if ev.get("dif_above_open_ended") else ""
            cross = ev.get("cross_date")
            cross_txt = f" 翻正@{cross}" if cross else ""
            span = (
                f"后续 {ev.get('dif_above_beg')}→{ev.get('dif_above_end')}"
                f"{open_mark} ({ev.get('dif_above_count')}日){cross_txt}"
            )
        else:
            span = "未形成后续区间"
        print(
            f"  {ev.get('date')}  {ev.get('signal')}  "
            f"DIF={ev.get('dif')} DEA={ev.get('dea')}  "
            f"基准收 {ev.get('base_close')}  |  {span}  |  "
            f"最大涨 {_pct(ev.get('max_close_gain'))}"
            f"@{ev.get('max_close_date') or '—'}  "
            f"最大跌 {_pct(ev.get('max_close_drop'))}"
            f"@{ev.get('max_close_drop_date') or '—'}"
        )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="股性：区间 MACD 金叉/即将金叉 + 后续 DIF≥DEA 段最大收盘涨/跌幅"
    )
    p.add_argument("code", nargs="?", help="股票代码，如 600519")
    p.add_argument("--beg", default="", help="起始日期 YYYY-MM-DD 或 YYYYMMDD")
    p.add_argument("--end", default="", help="结束日期，默认今天")
    p.add_argument(
        "--preset",
        default=DEFAULT_PRESET,
        choices=ALLOWED_PRESETS,
        help=f"MACD 预设，默认 {DEFAULT_PRESET}",
    )
    p.add_argument("--near-ratio", type=float, default=0.10, help="即将金叉相对缺口阈值")
    p.add_argument("--adjust", default="qfq", help="qfq/hfq/none，默认前复权")
    p.add_argument("--json", action="store_true", help="输出完整 JSON")
    args = p.parse_args(argv)

    if not args.code or not args.beg:
        p.error("须提供 code 与 --beg")

    try:
        pack = analyze_gene(
            args.code,
            args.beg,
            args.end,
            preset=args.preset,
            near_ratio=args.near_ratio,
            adjust=args.adjust,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(pack, ensure_ascii=False, indent=2, default=str))
    else:
        _print_text(pack)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
