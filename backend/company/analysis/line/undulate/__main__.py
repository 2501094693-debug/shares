"""CLI：个股相对基准收盘的四价涨跌幅 / 波动统计。

示例::

    python -m company.analysis.line.undulate 600519 --beg 2026-01-06
    python -m company.analysis.line.undulate 600519 --beg 20260106 --vol
    python -m company.analysis.line.undulate 600519 --beg 20260106 --end 20260301 --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[4]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from company.analysis.line.undulate.service import FACTORS, analyze_undulate
from company.analysis.line.undulate.volatility import analyze_volatility


def _fmt_pct(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v * 100:+.2f}%"


def _print_text(pack: dict) -> None:
    base = pack.get("base") or {}
    print(
        f"{pack.get('code')} {pack.get('name') or ''}  "
        f"[{pack.get('beg')} → {pack.get('end')}]  "
        f"共 {pack.get('count')} 个交易日  "
        f"（{'前复权' if pack.get('adjust') == 'qfq' else pack.get('adjust')}）"
    )
    print(
        f"  基准：相对 {_bar_close(base)} @ {base.get('date')} 收盘"
    )
    rng = pack.get("range") or {}
    for f in FACTORS:
        row = rng.get(f) or {}
        label = row.get("label") or f
        print(
            f"  {label} 范围: {_fmt_pct(row.get('min'))} @ {row.get('min_date')}"
            f"  ~  {_fmt_pct(row.get('max'))} @ {row.get('max_date')}"
        )


def _print_volatility(pack: dict) -> None:
    _print_text(pack)
    print("  波动统计（涨跌幅，样本标准差）：")
    stats = pack.get("stats") or {}
    for f in FACTORS:
        row = stats.get(f) or {}
        label = row.get("label") or f
        print(
            f"    {label}: 范围 {_fmt_pct(row.get('min'))} ~ {_fmt_pct(row.get('max'))}"
            f"  极差 {_fmt_pct(row.get('range'))}"
            f"  均值 {_fmt_pct(row.get('mean'))}"
            f"  标准差 {_fmt_pct(row.get('std'))}"
            f"  （样本 {row.get('count')}）"
        )
    end_date = next(
        (row.get("end_date") for row in stats.values() if row.get("end_date")), None
    )
    if end_date:
        print(f"  结束日 {end_date} 位于「均值=0、σ=单位」坐标轴：")
        for f in FACTORS:
            row = stats.get(f) or {}
            label = row.get("label") or f
            z = row.get("end_z")
            z_txt = f"{z:+.2f}σ" if z is not None else "—"
            print(
                f"    {label}: {_fmt_pct(row.get('end_pct'))}  →  {z_txt}"
            )


def _bar_close(base: dict) -> str:
    c = base.get("close")
    return f"{c}" if c is not None else "—"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="个股相对基准收盘的四价涨跌幅")
    p.add_argument("code", nargs="?", help="股票代码，如 600519")
    p.add_argument("--beg", default="", help="起始日期 YYYY-MM-DD 或 YYYYMMDD")
    p.add_argument("--end", default="", help="结束日期，默认今天")
    p.add_argument("--adjust", default="qfq", help="qfq/hfq/none，默认前复权")
    p.add_argument(
        "--vol",
        action="store_true",
        help="额外输出涨跌幅的均值 / 标准差 / 波动范围",
    )
    p.add_argument("--json", action="store_true", help="输出完整 JSON")
    args = p.parse_args(argv)

    if not args.code or not args.beg:
        p.error("须提供 code 与 --beg")

    try:
        if args.vol:
            pack = analyze_volatility(
                args.code, args.beg, args.end, adjust=args.adjust
            )
        else:
            pack = analyze_undulate(
                args.code, args.beg, args.end, adjust=args.adjust
            )
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(pack, ensure_ascii=False, indent=2))
    elif args.vol:
        _print_volatility(pack)
    else:
        _print_text(pack)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
