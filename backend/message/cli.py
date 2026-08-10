"""命令行入口。

在 backend 目录下::

    python -m message.cli 600519
    python -m message.cli 000001 --channel szse
    python -m message.cli 920000 --channel bse --days 180
    python -m message.cli 002731 --regulatory-only
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 允许直接 python message/cli.py
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from message.disclosure.http_util import detect_market, normalize_code
from message.disclosure.query import (
    query_announcements,
    query_company_messages,
    query_regulatory,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="查询公司交易所公告与监管信息")
    parser.add_argument("code", help="股票代码，如 600519 / 000001 / 920000")
    parser.add_argument(
        "--channel",
        default="auto",
        choices=["auto", "sse", "szse", "bse", "cninfo", "all"],
        help="公告检索通道，默认 auto",
    )
    parser.add_argument("--days", type=int, default=365, help="回溯天数，默认 365")
    parser.add_argument("--max-pages", type=int, default=5, help="每通道最多翻页数")
    parser.add_argument(
        "--regulatory-only",
        action="store_true",
        help="只查问询/处罚相关",
    )
    parser.add_argument(
        "--no-regulatory",
        action="store_true",
        help="综合查询时跳过监管信息",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="打印前 N 条，默认 10；0 表示全部",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="以 JSON 输出完整结果",
    )
    args = parser.parse_args(argv)

    code = normalize_code(args.code)
    market = detect_market(code)

    if args.regulatory_only:
        items = query_regulatory(
            code, days=args.days, max_pages=args.max_pages
        )
        payload = {
            "code": code,
            "market": market,
            "regulatory": items,
            "regulatory_count": len(items),
        }
    elif args.no_regulatory:
        items = query_announcements(
            code,
            channel=args.channel,
            days=args.days,
            max_pages=args.max_pages,
        )
        payload = {
            "code": code,
            "market": market,
            "notices": items,
            "notice_count": len(items),
        }
    else:
        payload = query_company_messages(
            args.code,
            channel=args.channel,
            include_regulatory=True,
            days=args.days,
            max_pages=args.max_pages,
        )

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"code={payload.get('code')} market={payload.get('market', '')}")
    if "notice_count" in payload:
        print(f"notices={payload['notice_count']}")
        rows = payload.get("notices") or []
        limit = len(rows) if args.limit <= 0 else args.limit
        for i, row in enumerate(rows[:limit], 1):
            print(
                f"  [{i}] {row.get('published_at', '')[:10]} "
                f"| {row.get('channel')} | {row.get('title')}"
            )
            if row.get("url"):
                print(f"       {row['url']}")
    if "regulatory_count" in payload:
        print(f"regulatory={payload['regulatory_count']}")
        rows = payload.get("regulatory") or []
        limit = len(rows) if args.limit <= 0 else args.limit
        for i, row in enumerate(rows[:limit], 1):
            print(
                f"  [{i}] {row.get('published_at', '')[:10]} "
                f"| {row.get('kind')} | {row.get('title')}"
            )
            if row.get("url"):
                print(f"       {row['url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
