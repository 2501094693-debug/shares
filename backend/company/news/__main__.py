"""python -m company.news

示例::

    python -m company.news 600519
    python -m company.news 600519 --kind cninfo --days 14
    python -m company.news 600519 --profile --sections all
    python -m company.news 600519 --press --outlet stcn,cs
    python -m company.news 600519 --regulatory
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from core.codes import detect_market, normalize_code
from company.news.feed import VALID_KINDS, collect_company_messages
from company.news.profile import query_company_profile
from company.news.query import query_company_messages, query_press, query_regulatory
from company.news.taxonomy.constants import ALL_SECTIONS, DEFAULT_SECTIONS, PRESS_OUTLETS


def _print_rows(rows: list, *, limit: int) -> None:
    n = len(rows) if limit <= 0 else min(limit, len(rows))
    for i, row in enumerate(rows[:n], 1):
        print(
            f"  [{i}] {str(row.get('published_at', ''))[:19]} "
            f"| {row.get('source') or row.get('channel')} | {row.get('title')}"
        )
        if row.get("url"):
            print(f"       {row['url']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="个股资讯集成：详情页分组 / 画像 / 七网 / 监管"
    )
    parser.add_argument("code", help="股票代码或公司名，如 600519 / 贵州茅台")
    parser.add_argument("--name", default="", help="公司简称（可选）")
    parser.add_argument(
        "--kind",
        default="",
        help="详情页分组: " + ",".join(VALID_KINDS) + "；空为全部",
    )
    parser.add_argument("--days", type=int, default=None, help="回溯天数")
    parser.add_argument("--max-pages", type=int, default=3, help="画像/七网翻页上限")
    parser.add_argument("--limit", type=int, default=5, help="每组打印条数，0=全部")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    parser.add_argument("--refresh", action="store_true", help="忽略磁盘缓存")
    parser.add_argument("--profile", action="store_true", help="系统性分类画像")
    parser.add_argument(
        "--sections",
        default="default",
        help=(
            "画像采集段：default="
            + ",".join(DEFAULT_SECTIONS)
            + "；all 或逗号组合="
            + ",".join(ALL_SECTIONS)
        ),
    )
    parser.add_argument("--press", action="store_true", help="只查七家指定披露媒体官网")
    parser.add_argument(
        "--outlet",
        default="all",
        help="七网 id，逗号分隔或 all。可选: " + ",".join(o["id"] for o in PRESS_OUTLETS),
    )
    parser.add_argument("--regulatory", action="store_true", help="只查问询/处罚相关")
    parser.add_argument(
        "--channel",
        default="auto",
        choices=["auto", "sse", "szse", "bse", "cninfo", "all"],
        help="公告通道（--regulatory 时忽略）",
    )
    args = parser.parse_args(argv)

    if args.profile:
        payload = query_company_profile(
            args.code,
            name=args.name,
            days=args.days if args.days is not None else 90,
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
        for cat, rows in (payload.get("groups") or {}).items():
            print(f"\n[{cat}] n={len(rows)}")
            _print_rows(rows, limit=args.limit)
        return 0

    if args.press:
        payload = query_press(
            args.code,
            outlet=args.outlet,
            days=args.days if args.days is not None else 31,
            max_pages=args.max_pages,
        )
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0
        print(
            f"code={payload.get('code')} name={payload.get('name')} "
            f"keyword={payload.get('keyword')} total={payload.get('count')}"
        )
        outlets = payload.get("outlets") or {}
        for o in PRESS_OUTLETS:
            rows = outlets.get(o["id"]) or []
            if args.outlet != "all" and o["id"] not in args.outlet:
                continue
            print(f"\n[{o['name']}/{o['paper']}] n={len(rows)}")
            _print_rows(rows, limit=args.limit)
        return 0

    if args.regulatory:
        code = normalize_code(args.code) or args.code
        items = query_regulatory(
            code,
            days=args.days if args.days is not None else 365,
            max_pages=args.max_pages,
        )
        payload = {
            "code": code,
            "market": detect_market(code),
            "regulatory": items,
            "regulatory_count": len(items),
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0
        print(f"code={code} market={payload['market']} regulatory={len(items)}")
        _print_rows(items, limit=args.limit)
        return 0

    if args.kind or args.days is not None or args.refresh:
        payload = collect_company_messages(
            normalize_code(args.code) or args.code,
            name=args.name,
            force_refresh=args.refresh,
            days=args.days if args.days is not None else 3,
            kind=args.kind,
        )
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0
        print(
            f"code={payload.get('code')} name={payload.get('name')} "
            f"kind={payload.get('kind')} days={payload.get('days')} "
            f"counts={payload.get('counts')}"
        )
        groups = payload.get("groups") or {}
        for key in VALID_KINDS:
            rows = groups.get(key) or []
            if args.kind and key != args.kind and args.kind not in {"news", "notices", "official"}:
                if key not in (args.kind,):
                    continue
            if not rows and args.kind and key != payload.get("kind"):
                continue
            print(f"\n[{key}] n={len(rows)}")
            _print_rows(rows, limit=args.limit)
        return 0

    payload = query_company_messages(
        args.code,
        channel=args.channel,
        include_regulatory=True,
        days=args.days if args.days is not None else 365,
        max_pages=args.max_pages,
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    print(
        f"code={payload.get('code')} market={payload.get('market')} "
        f"notices={payload.get('notice_count')} "
        f"regulatory={payload.get('regulatory_count')}"
    )
    print(f"\n[notices] n={payload.get('notice_count')}")
    _print_rows(payload.get("notices") or [], limit=args.limit)
    print(f"\n[regulatory] n={payload.get('regulatory_count')}")
    _print_rows(payload.get("regulatory") or [], limit=args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
