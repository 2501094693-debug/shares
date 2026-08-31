"""命令行：``python -m company.news.official.cninfo.cli``。"""

from __future__ import annotations

import argparse
import json
import logging
from typing import Any

from company.news.official.cninfo.fetch import fetch_announcements, fetch_market_announcements
from company.news.official.cninfo.params import resolve_org
from company.news.official.cninfo.request import download_announcements


def print_items(pack: dict[str, Any], limit: int, as_json: bool) -> None:
    if as_json:
        payload = dict(pack)
        if limit > 0:
            payload["items"] = (pack.get("items") or [])[:limit]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    items = pack.get("items") or []
    shown = items if limit <= 0 else items[:limit]
    extra = []
    if pack.get("code"):
        extra.append(pack["code"])
    if pack.get("name"):
        extra.append(pack["name"])
    if pack.get("org_id"):
        extra.append(pack["org_id"])
    print(
        " ".join(extra)
        + f"  column={pack.get('column')} tab={pack.get('tab')} "
        + f"seDate={pack.get('se_date')} count={pack.get('count')}"
        + (f"/{pack.get('total')}" if pack.get("total") else "")
    )
    if pack.get("error"):
        print(f"  error: {pack['error']}")
        return
    if not shown:
        print("  (empty)")
        return
    for i, row in enumerate(shown, 1):
        day = (row.get("published_at") or "")[:10]
        cat = row.get("category") or ""
        cat_bit = f" [{cat}]" if cat else ""
        print(f"  [{i}] {day}{cat_bit} {row.get('title')}")
        if row.get("url"):
            print(f"       {row['url']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="从巨潮资讯网拉取上市公司公告")
    parser.add_argument(
        "code",
        nargs="?",
        default="",
        help="股票代码或简称，如 600519 / 贵州茅台；与 --market 二选一",
    )
    parser.add_argument("--days", type=int, default=365, help="回溯天数，默认 365")
    parser.add_argument("--start", default="", help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end", default="", help="结束日期 YYYY-MM-DD")
    parser.add_argument(
        "--column",
        default="auto",
        help="sse / szse / bj / auto，默认按代码判断",
    )
    parser.add_argument(
        "--tab",
        default="fulltext",
        help="fulltext 公告 | relation 调研 | supervise 持续督导",
    )
    parser.add_argument(
        "--category",
        default="",
        help="分类别名，如 annual / 年报 / q1；多个用逗号分隔",
    )
    parser.add_argument("--keyword", default="", help="标题关键词")
    parser.add_argument("--plate", default="", help="板块，如 szmb / shkcp")
    parser.add_argument("--max-pages", type=int, default=5, help="最多翻页，默认 5")
    parser.add_argument("--limit", type=int, default=10, help="打印/下载前 N 条；0 为全部")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    parser.add_argument("--org-only", action="store_true", help="只解析 orgId，不查公告")
    parser.add_argument(
        "--market",
        default="",
        help="不指定个股时的全市场栏目：sse / szse / bj",
    )
    parser.add_argument("--download", default="", help="把公告 PDF 存到该目录")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if args.org_only:
        if not args.code:
            parser.error("--org-only 需要股票代码或简称")
        org = resolve_org(args.code)
        if args.json:
            print(json.dumps(org or {}, ensure_ascii=False, indent=2))
        elif org:
            print(
                f"{org.get('code')} {org.get('name') or ''}  "
                f"orgId={org.get('org_id')}  {org.get('category') or ''}"
            )
        else:
            print(f"找不到 orgId: {args.code}")
            return 1
        return 0

    start = args.start or None
    end = args.end or None
    category = args.category or None

    if args.market and not args.code:
        pack = fetch_market_announcements(
            column=args.market,
            category=category,
            keyword=args.keyword,
            plate=args.plate,
            start=start,
            end=end,
            days=args.days,
            max_pages=args.max_pages,
        )
    else:
        if not args.code:
            parser.error("请提供股票代码，或使用 --market 做全市场查询")
        pack = fetch_announcements(
            args.code,
            start=start,
            end=end,
            days=args.days,
            column=args.column,
            tab=args.tab,
            category=category,
            keyword=args.keyword,
            plate=args.plate,
            max_pages=args.max_pages,
        )

    print_items(pack, args.limit, args.json)

    if args.download:
        saved = download_announcements(
            pack.get("items") or [],
            args.download,
            limit=args.limit,
        )
        print(f"downloaded {len(saved)} files -> {args.download}")

    return 1 if pack.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())

