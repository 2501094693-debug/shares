"""python -m company.news.financialreport 600519"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[3]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from company.news.financialreport.fetcher import get_financial_report


def main() -> None:
    parser = argparse.ArgumentParser(description="东方财富 F10 财务报表")
    parser.add_argument("code", help="股票代码，如 600519")
    parser.add_argument(
        "--scope",
        default="merged",
        choices=("all", "merged", "main", "income", "balance", "cashflow", "lico"),
    )
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    data = get_financial_report(
        args.code,
        scope=args.scope,
        limit=args.limit,
        force=args.refresh,
    )
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
