"""CLI：股票 vs 指数日线四项对比。

示例::

    python -m company.analysis.line.compare 600519 --beg 2026-01-01
    python -m company.analysis.line.compare 600519 --beg 20260101 --indices 000300,000905
    python -m company.analysis.line.compare 600519 --beg 2026-01-01 --end 2026-03-01 --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[4]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from company.analysis.line.compare.codes import FACTOR_LABELS, FACTORS
from company.analysis.line.compare.service import (
    available_indices,
    compare_stock_vs_indices,
)


def _print_text(pack: dict) -> None:
    meta = pack.get("meta") or {}
    print(
        f"{meta.get('stock')} {meta.get('stock_name') or ''}  "
        f"{meta.get('beg')} ~ {meta.get('end')}"
    )
    for cmp_ in pack.get("comparisons") or []:
        idx = cmp_.get("index") or {}
        total = cmp_.get("total") or {}
        deviation = cmp_.get("deviation") or {}
        norm = cmp_.get("norm") or (pack.get("meta") or {}).get("norm") or {}
        print(
            f"\n=== vs {idx.get('code')} {idx.get('name') or ''}  "
            f"n={len(cmp_.get('dates') or [])}  "
            f"口径={norm.get('label') or norm.get('mode') or 'vol'}  "
            f"强弱={total.get('value')} ({total.get('level')})  "
            f"偏离={deviation.get('value')} ({deviation.get('level')})"
        )
        days = cmp_.get("days") or []
        show = days[-5:] if len(days) > 5 else days
        if len(days) > 5:
            print(f"（仅展示最近 {len(show)} 日 / 共 {len(days)} 日）")
        for day in show:
            print(f"  {day['date']}")
            stock = day.get("stock") or {}
            index = day.get("index") or {}
            factors = day.get("factors") or {}
            for f in FACTORS:
                label = FACTOR_LABELS[f]
                pair = factors.get(f) or {}
                print(
                    f"    {label}: 股={stock.get(f)} 指={index.get(f)} "
                    f"差={pair.get('dif')} {pair.get('dir')}"
                )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="股票 vs 指数日线四项对比")
    p.add_argument("code", nargs="?", help="股票代码，如 600519")
    p.add_argument("--beg", default="", help="起始日期 YYYY-MM-DD")
    p.add_argument("--end", default="", help="结束日期；空=今天")
    p.add_argument(
        "--indices",
        default="",
        help="逗号分隔指数码/名；空=上证/深成/沪深300/中证500/中证1000",
    )
    p.add_argument("--json", action="store_true", help="输出完整 JSON")
    p.add_argument("--meta", action="store_true", help="只打印可选指数目录")
    args = p.parse_args(argv)

    if args.meta:
        print(json.dumps(available_indices(), ensure_ascii=False, indent=2))
        return 0

    if not args.code or not args.beg:
        p.error("须提供 code 与 --beg")

    try:
        pack = compare_stock_vs_indices(
            args.code,
            beg=args.beg,
            end=args.end,
            indices=args.indices or None,
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
