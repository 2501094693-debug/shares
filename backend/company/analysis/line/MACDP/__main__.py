"""CLI：区间 MACDP。

示例::

    python -m company.analysis.line.MACDP 600519 --beg 2024-01-02
    python -m company.analysis.line.MACDP 600519 --beg 20240102 --end 20241231
    python -m company.analysis.line.MACDP 600519 --beg 2024-01-02 --fast 12 --slow 26 --signal 9
    python -m company.analysis.line.MACDP 600519 --beg 2024-01-02 --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[4]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from company.analysis.line.MACDP.core import (
    DEFAULT_FAST,
    DEFAULT_SIGNAL,
    DEFAULT_SLOW,
)
from company.analysis.line.MACDP.service import analyze_macdp


def _print_text(pack: dict) -> None:
    print(
        f"{pack.get('code')} {pack.get('name') or ''}  "
        f"[{pack.get('beg')} → {pack.get('end')}]  "
        f"共 {pack.get('count')} 个交易日  "
        f"（{'前复权' if pack.get('adjust') == 'qfq' else pack.get('adjust')}）"
    )
    print(
        f"  参数: fast={pack.get('fast')} slow={pack.get('slow')} "
        f"signal={pack.get('signal')}  "
        f"价格={pack.get('price_label')}({pack.get('price')})  "
        f"α={pack.get('alpha')}  dea_α={pack.get('dea_alpha')}"
    )
    latest = pack.get("latest") or {}
    print(
        f"  最新 {latest.get('date')}:  "
        f"avg={latest.get('price')}  "
        f"DIF={latest.get('dif')}  "
        f"DEA={latest.get('dea')}  "
        f"MACD={latest.get('macd')}"
    )
    items = list(pack.get("items") or [])
    if len(items) <= 8:
        show = items
    else:
        show = items[:3] + [{"date": "…"}] + items[-3:]
    for row in show:
        if row.get("date") == "…":
            print("    …")
            continue
        print(
            f"    {row.get('date')}  "
            f"DIF={row.get('dif')}  DEA={row.get('dea')}  MACD={row.get('macd')}"
        )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="区间日线 MACDP（均价 + 量加权快慢线 + 固定 DEA）"
    )
    p.add_argument("code", nargs="?", help="股票代码，如 600519")
    p.add_argument("--beg", default="", help="起始日期 YYYY-MM-DD 或 YYYYMMDD")
    p.add_argument("--end", default="", help="结束日期，默认今天")
    p.add_argument("--fast", type=int, default=DEFAULT_FAST, help="快线时长，默认 10")
    p.add_argument("--slow", type=int, default=DEFAULT_SLOW, help="慢线时长，默认 20")
    p.add_argument(
        "--signal", type=int, default=DEFAULT_SIGNAL, help="信号线时长，默认 7"
    )
    p.add_argument("--adjust", default="qfq", help="qfq/hfq/none，默认前复权")
    p.add_argument("--json", action="store_true", help="输出完整 JSON")
    args = p.parse_args(argv)

    if not args.code or not args.beg:
        p.error("须提供 code 与 --beg")

    try:
        pack = analyze_macdp(
            args.code,
            args.beg,
            args.end,
            fast=args.fast,
            slow=args.slow,
            signal=args.signal,
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
