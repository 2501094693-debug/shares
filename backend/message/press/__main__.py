"""python -m message.press

示例::

    python -m message.press 600519
    python -m message.press 贵州茅台 --outlet stcn,cs
    python -m message.press 600519 --days 180 --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from message.press.constants import OUTLETS
from message.press.query import query_press


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="查询公司在七家指定披露媒体上的相关消息"
    )
    parser.add_argument("code", help="股票代码或公司名，如 600519 / 贵州茅台")
    parser.add_argument(
        "--outlet",
        default="all",
        help=(
            "媒体 id，逗号分隔或 all。可选: "
            + ",".join(o["id"] for o in OUTLETS)
        ),
    )
    parser.add_argument("--days", type=int, default=365, help="回溯天数")
    parser.add_argument("--max-pages", type=int, default=4, help="东财每组关键词最多翻页")
    parser.add_argument(
        "--no-direct",
        action="store_true",
        help="跳过官网直连补充",
    )
    parser.add_argument("--limit", type=int, default=5, help="每家打印条数，0=全部")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args(argv)

    payload = query_press(
        args.code,
        outlet=args.outlet,
        days=args.days,
        max_pages=args.max_pages,
        include_direct=not args.no_direct,
    )

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(
        f"code={payload.get('code')} name={payload.get('name')} "
        f"keyword={payload.get('keyword')} total={payload.get('count')}"
    )
    counts = payload.get("counts") or {}
    outlets = payload.get("outlets") or {}
    for o in OUTLETS:
        oid = o["id"]
        if oid not in outlets and args.outlet != "all" and oid not in args.outlet:
            continue
        rows = outlets.get(oid) or []
        print(f"\n[{o['name']}/{o['paper']}] n={counts.get(oid, len(rows))}")
        limit = len(rows) if args.limit <= 0 else args.limit
        for i, row in enumerate(rows[:limit], 1):
            print(
                f"  [{i}] {str(row.get('published_at', ''))[:10]} "
                f"| {row.get('media_name') or row.get('why')} | {row.get('title')}"
            )
            if row.get("url"):
                print(f"       {row['url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
