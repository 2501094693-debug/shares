"""同花顺社区：手机客户端个股讨论、评论预览、讨论热度。

    python -m company.emotion.tonghuashun 600519
    python -m company.emotion.tonghuashun 600519 --replies --json
    python -m company.emotion.tonghuashun 600519 --days 7
    python -m company.emotion.tonghuashun --search 茅台
    python -m company.emotion.tonghuashun 600519 --rank
    python -m company.emotion.tonghuashun 600519 --scores
    python -m company.emotion.tonghuashun 600519 --all --json
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import date, datetime
from typing import Any

from company.emotion.tonghuashun.posts import (
    KINDS,
    SORTS,
    fetch_posts,
    query_page as query_post_page,
    resolve_kind,
    resolve_sort,
)
from company.emotion.tonghuashun.rank import fetch_hot_list, fetch_rank, query_hot_page
from company.emotion.tonghuashun.scores import fetch_scores, query_scores
from company.emotion.tonghuashun.search import search_posts, query_page as query_search_page
from company.emotion.tonghuashun._common import (
    CHANNEL_POSTS,
    SOURCE,
    list_page_url,
    mobile_page_url,
    print_items,
    rank_page_url,
    search_page_url,
)

__all__ = [
    "CHANNEL_POSTS",
    "KINDS",
    "SORTS",
    "SOURCE",
    "fetch_company",
    "fetch_hot_list",
    "fetch_posts",
    "fetch_rank",
    "fetch_scores",
    "list_page_url",
    "mobile_page_url",
    "query_hot_page",
    "query_post_page",
    "query_scores",
    "query_search_page",
    "rank_page_url",
    "resolve_kind",
    "resolve_sort",
    "search_page_url",
    "search_posts",
    "main",
]


def fetch_company(
    code_or_name: str,
    *,
    kind: str | None = "user",
    sort: str | None = "hot",
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = 3,
    max_pages: int = 3,
    with_replies: bool = False,
    max_reply_posts: int = 5,
) -> dict[str, Any]:
    """个股一次拉齐：手机讨论流 + 讨论热度。"""
    posts = fetch_posts(
        code_or_name,
        kind=kind,
        sort=sort,
        start=start,
        end=end,
        days=days,
        max_pages=max_pages,
        with_replies=with_replies,
        max_reply_posts=max_reply_posts,
    )
    scores = fetch_scores(code_or_name)
    rank = fetch_rank(code_or_name)
    code = posts.get("code") or scores.get("code") or rank.get("code") or ""
    name = posts.get("name") or scores.get("name") or rank.get("name") or ""
    return {
        "code": code,
        "name": name,
        "keyword": posts.get("keyword") or "",
        "source": SOURCE,
        "channel": "company",
        "kind": posts.get("kind") or kind,
        "sort": posts.get("sort") or sort,
        "posts": posts,
        "scores": scores,
        "rank": rank,
        "count": int(posts.get("count") or 0),
        "total": int(posts.get("total") or 0),
        "items": posts.get("items") or [],
        "page": posts.get("page") or mobile_page_url(str(code)),
        "error": posts.get("error") or scores.get("error") or rank.get("error") or "",
        "begin_date": posts.get("begin_date") or "",
        "end_date": posts.get("end_date") or "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="同花顺社区：手机客户端个股讨论 / 评论 / 讨论热度")
    parser.add_argument(
        "code",
        nargs="?",
        default="",
        help="股票代码或公司简称；--search 时可省略",
    )
    parser.add_argument("--days", type=int, default=None, help="回溯天数；默认不截日期，只按页数")
    parser.add_argument("--start", default="", help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end", default="", help="结束日期 YYYY-MM-DD")
    parser.add_argument("--kind", default="user", help="仅 user（手机讨论流）")
    parser.add_argument("--sort", default="hot", help="排序：hot 推荐 / time 最新")
    parser.add_argument("--search", default="", help="关键词；能解析成股票则拉该股讨论")
    parser.add_argument("--replies", action="store_true", help="附带列表里的评论预览")
    parser.add_argument("--rank", action="store_true", help="个股讨论热度名次")
    parser.add_argument("--scores", action="store_true", help="个股热度快照")
    parser.add_argument("--all", action="store_true", help="讨论流 + 热度")
    parser.add_argument("--max-pages", type=int, default=3, help="最多翻页，默认 3")
    parser.add_argument("--max-reply-posts", type=int, default=5, help="列表附带评论时最多几篇帖")
    parser.add_argument("--limit", type=int, default=10, help="打印前 N 条；0 为全部")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    start = args.start or None
    end = args.end or None
    code = args.code

    if args.search:
        pack = search_posts(
            args.search,
            code=code,
            start=start,
            end=end,
            days=args.days,
            max_pages=args.max_pages,
        )
        print_items(pack, args.limit, args.json)
        return 1 if pack.get("error") else 0

    if not code:
        parser.error("请提供股票代码，或使用 --search")

    if args.all:
        pack = fetch_company(
            code,
            kind=args.kind,
            sort=args.sort,
            start=start,
            end=end,
            days=args.days if args.days is not None else 3,
            max_pages=args.max_pages,
            with_replies=args.replies,
            max_reply_posts=args.max_reply_posts,
        )
        if args.json:
            payload = dict(pack)
            if args.limit > 0:
                payload["items"] = (pack.get("items") or [])[: args.limit]
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print_items(
                {
                    **pack,
                    "items": (pack.get("posts") or {}).get("items") or [],
                    "channel": (pack.get("posts") or {}).get("channel") or CHANNEL_POSTS,
                    "count": (pack.get("posts") or {}).get("count") or 0,
                    "total": (pack.get("posts") or {}).get("total") or 0,
                },
                args.limit,
                False,
            )
            print_items(pack.get("scores") or {}, args.limit, False)
            print_items(pack.get("rank") or {}, args.limit, False)
        return 1 if pack.get("error") else 0

    if args.rank:
        pack = fetch_rank(code)
        print_items(pack, args.limit, args.json)
        return 1 if pack.get("error") else 0

    if args.scores:
        pack = fetch_scores(code)
        print_items(pack, args.limit, args.json)
        return 1 if pack.get("error") else 0

    pack = fetch_posts(
        code,
        kind=args.kind,
        sort=args.sort,
        start=start,
        end=end,
        days=args.days,
        max_pages=args.max_pages,
        with_replies=args.replies,
        max_reply_posts=args.max_reply_posts,
    )
    print_items(pack, args.limit, args.json)
    return 1 if pack.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
