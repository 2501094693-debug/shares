"""python -m company.news.periodicreport 600519"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[3]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from company.news.periodicreport.fetcher import get_periodic_report


def main() -> None:
    parser = argparse.ArgumentParser(description="上市公司定期报告")
    parser.add_argument("code", help="股票代码，如 600519")
    parser.add_argument("--period", default="", help="如 2025-annual / 2025年报")
    parser.add_argument("--days", type=int, default=1825)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    data = get_periodic_report(
        args.code,
        days=args.days,
        period=args.period,
        force=args.refresh,
    )
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
