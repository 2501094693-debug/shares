"""东方财富社区：股吧帖子、正文、回复、搜索、人气榜、千股千评。

东财没有文档化的公开社区 API，以下全部是官网前端 XHR / 页面内嵌 JSON。
``gbapi.eastmoney.com`` 需要签名，当前不可用。

    python -m company.emotion.eastmoney 600519
    python -m company.emotion.eastmoney 600519 --days 3 --sort time
    python -m company.emotion.eastmoney 600519 --kind news
    python -m company.emotion.eastmoney 600519 --kind hot
    python -m company.emotion.eastmoney 600519 --kind qa
    python -m company.emotion.eastmoney 600519 --replies --max-reply-posts 5
    python -m company.emotion.eastmoney --post 1759863886
    python -m company.emotion.eastmoney 600519 --post 1759863886 --replies
    python -m company.emotion.eastmoney --search 茅台
    python -m company.emotion.eastmoney --rank
    python -m company.emotion.eastmoney 600519 --rank
    python -m company.emotion.eastmoney 600519 --scores
    python -m company.emotion.eastmoney 600519 --all --json
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import date, datetime
from typing import Any

from company.emotion.eastmoney.article import fetch_article
from company.emotion.eastmoney.posts import (
    KINDS,
    SORTS,
    fetch_posts,
    query_page as query_post_page,
    resolve_kind,
    resolve_sort,
)
from company.emotion.eastmoney.rank import (
    fetch_hot_list,
    fetch_rank,
    query_hot_page,
    query_rank_history,
    query_rank_intraday,
)
from company.emotion.eastmoney.replies import fetch_replies, query_page as query_reply_page
from company.emotion.eastmoney.scores import fetch_scores, query_scores
from company.emotion.eastmoney.search import search_posts, query_page as query_search_page
from company.emotion.eastmoney._common import (
    CHANNEL_POSTS,
    SOURCE,
    list_page_url,
    post_url,
    print_items,
    rank_page_url,
    scores_page_url,
    search_page_url,
)

__all__ = [
    "KINDS",
    "SORTS",
    "SOURCE",
    "fetch_article",
    "fetch_company",
    "fetch_hot_list",
    "fetch_posts",
    "fetch_rank",
    "fetch_replies",
    "fetch_scores",
    "list_page_url",
    "post_url",
    "query_hot_page",
    "query_post_page",
    "query_rank_history",
    "query_rank_intraday",
    "query_reply_page",
    "query_scores",
    "query_search_page",
    "rank_page_url",
    "resolve_kind",
    "resolve_sort",
    "scores_page_url",
    "search_page_url",
    "search_posts",
    "main",
]


def fetch_company(
    code_or_name: str,
    *,
    kind: str | None = "all",
    sort: str | None = "time",
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = 3,
    max_pages: int = 3,
    with_replies: bool = False,
    max_reply_posts: int = 5,
) -> dict[str, Any]:
    """个股一次拉齐：股吧帖子 + 千股千评 + 人气排名。"""
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
        "page": posts.get("page") or list_page_url(str(code)),
        "error": posts.get("error") or scores.get("error") or rank.get("error") or "",
        "begin_date": posts.get("begin_date") or "",
        "end_date": posts.get("end_date") or "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="东方财富社区：股吧帖子 / 正文 / 回复 / 搜索 / 人气榜 / 千股千评"
    )
    parser.add_argument(
        "code",
        nargs="?",
        default="",
        help="股票代码或公司简称；--search / --rank / --post 时可省略。配合 --post 时作为帖子所属代码",
    )
    parser.add_argument("--days", type=int, default=None, help="回溯天数；帖子默认不截日期，只按页数")
    parser.add_argument("--start", default="", help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end", default="", help="结束日期 YYYY-MM-DD")
    parser.add_argument(
        "--kind",
        default="all",
        help="帖子分类：all / news / reports / notices / margin / other / qa / meeting / hot",
    )
    parser.add_argument("--sort", default="time", help="排序：time 发帖时间 / reply 最新回复 / hot 热门")
    parser.add_argument("--search", default="", help="关键词搜股吧帖")
    parser.add_argument("--post", default="", help="帖子 ID 或 URL，拉正文")
    parser.add_argument("--replies", action="store_true", help="附带评论；配合 --post 或个股列表")
    parser.add_argument("--rank", action="store_true", help="人气榜；无 code 为全市场，有 code 为个股")
    parser.add_argument("--scores", action="store_true", help="千股千评（综合得分 / 关注指数）")
    parser.add_argument("--all", action="store_true", help="帖子 + 千股千评 + 人气")
    parser.add_argument("--max-pages", type=int, default=3, help="最多翻页，默认 3")
    parser.add_argument("--max-reply-posts", type=int, default=5, help="列表附带评论时最多拉几篇帖")
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
            sort=args.sort,
            max_pages=args.max_pages,
        )
        print_items(pack, args.limit, args.json)
        return 1 if pack.get("error") else 0

    if args.post:
        if args.replies and not args.json:
            pack = fetch_article(
                args.post,
                code=code,
                with_replies=True,
                max_reply_pages=args.max_pages,
            )
            _print_article(pack, args.limit)
            replies = {
                "channel": "guba_reply",
                "code": pack.get("code") or "",
                "count": len(pack.get("replies") or []),
                "total": pack.get("reply_total") or 0,
                "items": pack.get("replies") or [],
                "error": pack.get("replies_error") or "",
            }
            print_items(replies, args.limit, False)
            return 1 if pack.get("error") else 0
        if args.replies:
            pack = fetch_article(
                args.post,
                code=code,
                with_replies=True,
                max_reply_pages=args.max_pages,
            )
            print_items(pack, 0, True)
            return 1 if pack.get("error") else 0
        pack = fetch_article(args.post, code=code)
        if args.json:
            print_items(pack, 0, True)
        else:
            _print_article(pack, args.limit)
        return 1 if pack.get("error") else 0

    if args.rank and not code:
        pack = fetch_hot_list(page=1, page_size=max(args.limit, 20) if args.limit else 50)
        print_items(pack, args.limit, args.json)
        return 1 if pack.get("error") else 0

    if not code and not args.rank:
        parser.error("请提供股票代码，或使用 --search / --rank / --post")

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
                    "channel": CHANNEL_POSTS,
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
        max_reply_pages=args.max_pages,
    )
    print_items(pack, args.limit, args.json)
    return 1 if pack.get("error") else 0


def _print_article(pack: dict[str, Any], limit: int) -> None:
    from company.emotion.eastmoney._common import cli_print

    if pack.get("error"):
        cli_print(f"error: {pack['error']}")
        return
    bits = [
        pack.get("published_at") or "",
        pack.get("author") or pack.get("media_name") or "",
        pack.get("title") or "",
    ]
    cli_print("  ".join(b for b in bits if b))
    cli_print(pack.get("url") or "")
    content = pack.get("content") or ""
    cli_print(content if limit <= 0 else content[: max(200, limit * 80)])


if __name__ == "__main__":
    raise SystemExit(main())
