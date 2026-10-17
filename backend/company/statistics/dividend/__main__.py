"""python -m company.statistics.dividend 600519"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[3]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from company.statistics.dividend.fetcher import get_dividends


def main() -> None:
    parser = argparse.ArgumentParser(description="个股分红（东财 / 同花顺）")
    parser.add_argument("code", help="股票代码，如 600519")
    parser.add_argument(
        "--source",
        default="eastmoney",
        choices=("eastmoney", "ths"),
        help="数据源：eastmoney（默认，按报告期 + F10）/ ths（同花顺，含特别分红派现总额）",
    )
    parser.add_argument(
        "--scope",
        default="all",
        choices=("all", "detail", "history", "summary"),
        help="仅 source=eastmoney 时生效",
    )
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    data = get_dividends(
        args.code,
        scope=args.scope,
        limit=args.limit,
        force=args.refresh,
        source=args.source,
    )
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
