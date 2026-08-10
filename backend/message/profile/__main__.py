"""python -m message.profile

示例::

    python -m message.profile 600519
    python -m message.profile 600519 --sections all --days 90
    python -m message.profile 600519 --sections disclosure,regulatory --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from message.profile.query import query_company_profile
from message.taxonomy.constants import ALL_SECTIONS, DEFAULT_SECTIONS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="查询公司分类信息画像（disclosure/regulatory/press/news/research）"
    )
    parser.add_argument("code", help="股票代码或公司名")
    parser.add_argument("--name", default="", help="公司简称（可选）")
    parser.add_argument(
        "--sections",
        default="default",
        help=(
            "采集段：default="
            + ",".join(DEFAULT_SECTIONS)
            + "；或 all / 逗号组合="
            + ",".join(ALL_SECTIONS)
        ),
    )
    parser.add_argument("--days", type=int, default=90, help="回溯天数")
    parser.add_argument("--max-pages", type=int, default=3, help="各通道翻页上限")
    parser.add_argument("--limit", type=int, default=3, help="每类打印条数，0=全部")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args(argv)

    payload = query_company_profile(
        args.code,
        name=args.name,
        days=args.days,
        sections=args.sections,
        max_pages=args.max_pages,
    )

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(
        f"code={payload.get('code')} name={payload.get('name')} "
        f"days={payload.get('days')} sections={payload.get('sections')}"
    )
    print(f"counts={payload.get('counts')}")
    if payload.get("errors"):
        print(f"errors={payload.get('errors')}")

    groups = payload.get("groups") or {}
    for cat, rows in groups.items():
        print(f"\n[{cat}] n={len(rows)}")
        limit = len(rows) if args.limit <= 0 else args.limit
        for i, row in enumerate(rows[:limit], 1):
            print(
                f"  [{i}] {str(row.get('published_at', ''))[:10]} "
                f"| {row.get('source_tier')} | {row.get('subcategory')} "
                f"| {row.get('title')}"
            )
            if row.get("url"):
                print(f"       {row['url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
