"""``python -m company.line.entrust 600519``

``python -m company.line.entrust 600519 --price-levels --limit 5``
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[3]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from company.line.entrust.fetcher import fetch_entrust


def main() -> int:
    parser = argparse.ArgumentParser(description="同花顺委托盘口 / 买卖队列探针")
    parser.add_argument("code", help="股票代码，如 600519")
    parser.add_argument("--depth", default="5", help="档位数，当前 thsdk 仅支持 5")
    parser.add_argument(
        "--price-levels",
        action="store_true",
        help="附带当日分价成交（非排队委托）",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="预览时截断 bids/asks/price_levels 条数，0=全部",
    )
    parser.add_argument("--no-permissions", action="store_true", help="跳过权限探测")
    args = parser.parse_args()

    pack = fetch_entrust(
        args.code,
        depth=args.depth,
        with_price_levels=args.price_levels,
        with_permissions=not args.no_permissions,
    )
    if args.limit and args.limit > 0:
        pack = dict(pack)
        pack["bids"] = (pack.get("bids") or [])[: args.limit]
        pack["asks"] = (pack.get("asks") or [])[: args.limit]
        if "price_levels" in pack:
            levels = pack.get("price_levels") or []
            pack["price_levels"] = levels[: args.limit]
            pack["price_levels_total"] = len(levels)

    print(json.dumps(pack, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
