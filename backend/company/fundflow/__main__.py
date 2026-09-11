"""python -m company.fundflow 600519"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from company.fundflow.fetcher import get_fund_flow


def main() -> None:
    parser = argparse.ArgumentParser(description="东方财富个股资金流向")
    parser.add_argument("code", help="股票代码，如 600519")
    parser.add_argument(
        "--scope",
        default="daily",
        choices=("daily", "minute", "snapshot"),
    )
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--klt", type=int, default=1)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    data = get_fund_flow(
        args.code,
        scope=args.scope,
        limit=args.limit,
        klt=args.klt,
        force=args.refresh,
    )
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
