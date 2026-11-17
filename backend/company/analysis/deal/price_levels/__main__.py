"""python -m company.analysis.deal.price_levels 600519
python -m company.analysis.deal.price_levels 600519 --limit 10
python -m company.analysis.deal.price_levels 600519 --around 1450 --span 5
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[4]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from company.analysis.deal.price_levels.service import fetch_price_levels_pack


def main() -> None:
    parser = argparse.ArgumentParser(description="同花顺当日分价表（需实盘登录）")
    parser.add_argument("code", help="股票代码，如 600519")
    parser.add_argument("--limit", type=int, default=10, help="预览档数，0=全部")
    parser.add_argument("--around", type=float, default=None, help="只看某价附近，如 1450")
    parser.add_argument(
        "--span",
        type=float,
        default=5.0,
        help="配合 --around 的半宽（元），默认 5",
    )
    args = parser.parse_args()
    pack = fetch_price_levels_pack(
        args.code,
        around=args.around,
        span=args.span,
        limit=args.limit,
    )
    print(json.dumps(pack, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
