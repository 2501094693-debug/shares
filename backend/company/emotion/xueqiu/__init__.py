"""雪球社区：讨论帖、正文、评论、搜索、热股榜、热帖、关注快照。

雪球没有文档化的公开社区 API，以下全部是官网前端 XHR，需要 ``xq_a_token``。
token 优先读 ``XUEQIU_TOKEN`` / ``XUEQIU_COOKIES``，否则访问首页获取。

    python -m company.emotion.xueqiu 600519
    python -m company.emotion.xueqiu 600519 --days 7 --sort time
    python -m company.emotion.xueqiu 600519 --kind trans
    python -m company.emotion.xueqiu 600519 --sort hot
    python -m company.emotion.xueqiu 600519 --replies --max-reply-posts 5
    python -m company.emotion.xueqiu --post 406619710
    python -m company.emotion.xueqiu --post 406619710 --replies
    python -m company.emotion.xueqiu --search 茅台
    python -m company.emotion.xueqiu --rank
    python -m company.emotion.xueqiu --rank --market us
    python -m company.emotion.xueqiu 600519 --rank
    python -m company.emotion.xueqiu 600519 --scores
    python -m company.emotion.xueqiu 600519 --fans
    python -m company.emotion.xueqiu --hot
    python -m company.emotion.xueqiu 600519 --all --json
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import date, datetime
from typing import Any

from company.emotion.xueqiu.article import fetch_article, query_show
from company.emotion.xueqiu.posts import (
    KINDS,
    fetch_posts,
    query_page as query_post_page,
    resolve_kind,
)
from company.emotion.xueqiu.rank import (
    MARKETS,
    MARKET_LABELS,
    fetch_hot_list,
    fetch_hot_posts,
    fetch_rank,
    query_hot_page,
    query_hot_posts_page,
    rank_page_url,
    resolve_market,
)
from company.emotion.xueqiu.replies import fetch_replies, query_page as query_reply_page
from company.emotion.xueqiu.scores import (
    fetch_followers,
    fetch_scores,
    query_followers,
    query_hot_users,
    query_popstocks,
    query_scores,
)
from company.emotion.xueqiu.search import search_posts, query_page as query_search_page
from company.emotion.xueqiu._common import (
    CHANNEL_POSTS,
    SOURCE,
    article_url,
    current_token,
    print_items,
    search_page_url,
    set_token,
    stock_page_url,
)
from company.news.xueqiu.search import SORTS, resolve_sort

__all__ = [
    "CHANNEL_POSTS",
    "KINDS",
    "MARKETS",
    "MARKET_LABELS",
    "SORTS",
    "SOURCE",
    "article_url",
    "current_token",
    "fetch_article",
    "fetch_company",
    "fetch_followers",
    "fetch_hot_list",
    "fetch_hot_posts",
    "fetch_posts",
    "fetch_rank",
    "fetch_replies",
    "fetch_scores",
    "query_followers",
    "query_hot_page",
    "query_hot_posts_page",
    "query_hot_users",
    "query_popstocks",
    "query_post_page",
    "query_reply_page",
    "query_scores",
    "query_search_page",
    "query_show",
    "rank_page_url",
    "resolve_kind",
    "resolve_market",
    "resolve_sort",
    "search_page_url",
    "search_posts",
    "set_token",
    "stock_page_url",
    "main",
]


def fetch_company(
    code_or_name: str,
    *,
    kind: str | None = "user",
    sort: str | None = "time",
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = 3,
    max_pages: int = 3,
    with_replies: bool = False,
    max_reply_posts: int = 5,
    market: str = "cn",
) -> dict[str, Any]:
    """个股一次拉齐：讨论帖 + 社区快照 + 热股名次。"""
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
        max_reply_pages=max_pages,
    )
    scores = fetch_scores(code_or_name)
    rank = fetch_rank(code_or_name, market=market)
    code = posts.get("code") or scores.get("code") or rank.get("code") or ""
    name = posts.get("name") or scores.get("name") or rank.get("name") or ""
    symbol = posts.get("symbol") or scores.get("symbol") or rank.get("symbol") or ""
    return {
        "code": code,
        "name": name,
        "symbol": symbol,
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
        "page": posts.get("page") or stock_page_url(str(symbol or code)),
        "error": posts.get("error") or scores.get("error") or rank.get("error") or "",
        "begin_date": posts.get("begin_date") or "",
        "end_date": posts.get("end_date") or "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="雪球社区：讨论帖 / 正文 / 评论 / 搜索 / 热股 / 热帖 / 关注快照"
    )
    parser.add_argument(
        "code",
        nargs="?",
        default="",
        help="股票代码或公司简称；--search / --rank / --post / --hot 时可省略",
    )
    parser.add_argument("--days", type=int, default=None, help="回溯天数；默认不截日期，只按页数")
    parser.add_argument("--start", default="", help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end", default="", help="结束日期 YYYY-MM-DD")
    parser.add_argument(
        "--kind",
        default="user",
        help="讨论来源：user 讨论 / trans 交易 / all 全部",
    )
    parser.add_argument("--sort", default="time", help="排序：time 最新 / alpha 热门 / reply 评论")
    parser.add_argument("--search", default="", help="关键词搜帖")
    parser.add_argument("--post", default="", help="状态 ID 或 URL，拉正文")
    parser.add_argument("--replies", action="store_true", help="附带评论；配合 --post 或个股列表")
    parser.add_argument("--rank", action="store_true", help="热股榜；无 code 为全市场，有 code 为个股名次")
    parser.add_argument("--market", default="cn", help="热股市场：cn / hk / us / global / follow")
    parser.add_argument("--scores", action="store_true", help="个股社区快照（关注人数 / 热门用户）")
    parser.add_argument("--fans", action="store_true", help="关注该股的用户列表")
    parser.add_argument("--hot", action="store_true", help="全站热帖")
    parser.add_argument("--all", action="store_true", help="讨论 + 社区快照 + 热股名次")
    parser.add_argument("--token", default="", help="xq_a_token；也可用环境变量 XUEQIU_TOKEN")
    parser.add_argument("--cookies", default="", help="浏览器整段 Cookie；也可用环境变量 XUEQIU_COOKIES")
    parser.add_argument("--max-pages", type=int, default=3, help="最多翻页，默认 3")
    parser.add_argument("--max-reply-posts", type=int, default=5, help="列表附带评论时最多拉几篇帖")
    parser.add_argument("--limit", type=int, default=10, help="打印前 N 条；0 为全部")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.token or args.cookies:
        set_token(args.token, args.cookies)
    start = args.start or None
    end = args.end or None
    code = args.code

    if args.search:
        pack = search_posts(
            args.search,
            code=code,
            source=args.kind if args.kind != "user" else "all",
            sort=args.sort,
            start=start,
            end=end,
            days=args.days,
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
                "channel": "xq_reply",
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

    if args.hot:
        pack = fetch_hot_posts(max_pages=args.max_pages)
        print_items(pack, args.limit, args.json)
        return 1 if pack.get("error") else 0

    if args.rank and not code:
        pack = fetch_hot_list(
            market=args.market,
            page=1,
            page_size=max(args.limit, 20) if args.limit else 50,
        )
        print_items(pack, args.limit, args.json)
        return 1 if pack.get("error") else 0

    if not code and not args.rank:
        parser.error("请提供股票代码，或使用 --search / --rank / --post / --hot")

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
            market=args.market,
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
        pack = fetch_rank(code, market=args.market)
        print_items(pack, args.limit, args.json)
        return 1 if pack.get("error") else 0

    if args.scores:
        pack = fetch_scores(code)
        print_items(pack, args.limit, args.json)
        return 1 if pack.get("error") else 0

    if args.fans:
        pack = fetch_followers(code, max_pages=args.max_pages)
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
    from company.emotion.xueqiu._common import cli_print

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
