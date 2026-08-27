"""命令行：默认拉逐笔成交，``--kind orders`` 拉逐笔委托。

    python -m company.line.original 600519
    python -m company.line.original 600519 --pos -20
    python -m company.line.original 000001 --kind orders --limit 8
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[3]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from company.line.original.client import IFindError
from company.line.original.orders import _print_preview as print_orders
from company.line.original.orders import fetch_orders
from company.line.original.ticks import _print_preview as print_ticks
from company.line.original.ticks import fetch_transactions


def main() -> int:
    parser = argparse.ArgumentParser(description="从 iFinD 拉取逐笔成交或逐笔委托")
    parser.add_argument("code", nargs="?", default="600519", help="股票代码，如 600519")
    parser.add_argument(
        "--kind",
        choices=("transactions", "orders", "ticks"),
        default="transactions",
        help="transactions/ticks=成交，orders=委托",
    )
    parser.add_argument("--pos", default="0", help="0=当天全部；-20 或 20=最近 20 笔")
    parser.add_argument("--start", default="", help="开始时间 YYYY-MM-DD[ HH:MM:SS]")
    parser.add_argument("--end", default="", help="结束时间 YYYY-MM-DD[ HH:MM:SS]")
    parser.add_argument("--limit", type=int, default=5, help="预览最近笔数")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    kind = "orders" if args.kind == "orders" else "transactions"
    try:
        if kind == "orders":
            pack = fetch_orders(args.code, pos=args.pos, start=args.start, end=args.end)
            print_orders(pack, args.limit)
        else:
            pack = fetch_transactions(args.code, pos=args.pos, start=args.start, end=args.end)
            print_ticks(pack, args.limit)
    except (IFindError, ValueError) as exc:
        print(exc)
        return 1
    return 0 if pack.get("source") else 1


if __name__ == "__main__":
    raise SystemExit(main())
