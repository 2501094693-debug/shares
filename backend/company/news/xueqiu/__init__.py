"""雪球新闻：个股资讯、公告、研报、讨论、7×24 快讯、栏目流、正文。

雪球没有文档化的公开新闻 API，以下全部是官网前端 XHR，需要 ``xq_a_token``。
token 优先读 ``XUEQIU_TOKEN`` / ``XUEQIU_COOKIES``，否则访问首页获取。

    python -m company.news.xueqiu 600519
    python -m company.news.xueqiu 贵州茅台 --days 7
    python -m company.news.xueqiu 600519 --notices --days 90
    python -m company.news.xueqiu 600519 --reports
    python -m company.news.xueqiu 600519 --discuss
    python -m company.news.xueqiu --flash
    python -m company.news.xueqiu --flash --stock 600519
    python -m company.news.xueqiu --column headline
    python -m company.news.xueqiu --search 茅台
    python -m company.news.xueqiu --article 123456789
    python -m company.news.xueqiu 600519 --all --json
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import date, datetime
from typing import Any

from company.news.xueqiu.article import fetch_article
from company.news.xueqiu.columns import (
    COLUMNS,
    COLUMN_LABELS,
    column_page_url,
    fetch_column_news,
    query_page as query_column_page,
    resolve_column,
)
from company.news.xueqiu.flash import fetch_flash, query_page as query_flash_page
from company.news.xueqiu.news import fetch_news, query_page, search_news
from company.news.xueqiu.notices import fetch_notices, query_page as query_notice_page
from company.news.xueqiu.reports import fetch_reports, query_page as query_report_page
from company.news.xueqiu.search import (
    SEARCH_SOURCES,
    SORTS,
    fetch_discuss,
    query_keyword_page,
    query_page as query_search_page,
    search_posts,
)
from company.news.xueqiu._common import (
    SOURCE,
    TIMELINE_SOURCES,
    article_url,
    current_token,
    print_items,
    query_quote,
    query_timeline,
    resolve_keyword,
    search_page_url,
    set_token,
    stock_page_url,
    xq_symbol,
)

__all__ = [
    "COLUMNS",
    "COLUMN_LABELS",
    "SEARCH_SOURCES",
    "SORTS",
    "SOURCE",
    "TIMELINE_SOURCES",
    "article_url",
    "column_page_url",
    "current_token",
    "fetch_article",
    "fetch_column_news",
    "fetch_company",
    "fetch_discuss",
    "fetch_flash",
    "fetch_news",
    "fetch_notices",
    "fetch_reports",
    "query_column_page",
    "query_flash_page",
    "query_keyword_page",
    "query_notice_page",
    "query_page",
    "query_quote",
    "query_report_page",
    "query_search_page",
    "query_timeline",
    "resolve_column",
    "resolve_keyword",
    "search_news",
    "search_page_url",
    "search_posts",
    "set_token",
    "stock_page_url",
    "xq_symbol",
]


def fetch_company(
    code_or_name: str,
    *,
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = 31,
    max_pages: int = 3,
    strict: bool = False,
) -> dict[str, Any]:
    """个股一次拉齐：资讯 + 公告 + 研报。"""
    news = fetch_news(
        code_or_name,
        start=start,
        end=end,
        days=days,
        max_pages=max_pages,
        strict=strict,
    )
    notices = fetch_notices(
        code_or_name,
        start=start,
        end=end,
        days=days if days is not None else 365,
        max_pages=max_pages,
        strict=strict,
    )
    reports = fetch_reports(
        code_or_name,
        start=start,
        end=end,
        days=days,
        max_pages=max_pages,
        strict=strict,
    )
    code = news.get("code") or notices.get("code") or reports.get("code") or ""
    name = news.get("name") or notices.get("name") or reports.get("name") or ""
    symbol = news.get("symbol") or notices.get("symbol") or reports.get("symbol") or ""
    return {
        "code": code,
        "name": name,
        "keyword": news.get("keyword") or notices.get("keyword") or "",
        "symbol": symbol,
        "source": SOURCE,
        "channel": "company",
        "news": news,
        "notices": notices,
        "reports": reports,
        "count": int(news.get("count") or 0)
        + int(notices.get("count") or 0)
        + int(reports.get("count") or 0),
        "items": (news.get("items") or [])
        + (notices.get("items") or [])
        + (reports.get("items") or []),
        "page": stock_page_url(str(symbol or code or code_or_name)),
        "error": news.get("error") or notices.get("error") or reports.get("error") or "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="雪球新闻接口：个股资讯 / 公告 / 研报 / 讨论 / 快讯 / 栏目 / 正文")
    parser.add_argument(
        "code",
        nargs="?",
        default="",
        help="股票代码或公司简称；--flash / --column / --article / --search 时可省略",
    )
    parser.add_argument("--days", type=int, default=None, help="回溯天数；资讯默认 31，公告默认 365，讨论默认 7")
    parser.add_argument("--start", default="", help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end", default="", help="结束日期 YYYY-MM-DD")
    parser.add_argument("--strict", action="store_true", help="标题或摘要必须命中简称/代码")
    parser.add_argument("--flash", action="store_true", help="7×24 全市场快讯")
    parser.add_argument("--stock", default="", help="快讯事后按关联股票过滤")
    parser.add_argument("--since-id", default="", help="快讯增量水位 id")
    parser.add_argument("--notices", action="store_true", help="个股公告")
    parser.add_argument("--reports", action="store_true", help="个股研报")
    parser.add_argument("--discuss", action="store_true", help="个股讨论")
    parser.add_argument("--trans", action="store_true", help="个股交易动态")
    parser.add_argument(
        "--source",
        default="",
        help="讨论 source：all / user / trans；栏目不用这个",
    )
    parser.add_argument("--sort", default="time", help="讨论/搜索排序：time / alpha / reply")
    parser.add_argument("--column", default="", help="首页栏目：headline / cn / hk / us / fund / today")
    parser.add_argument("--search", default="", help="关键词搜帖")
    parser.add_argument("--article", default="", help="状态 id 或 URL，拉正文")
    parser.add_argument("--all", action="store_true", help="资讯 + 公告 + 研报")
    parser.add_argument("--token", default="", help="xq_a_token；也可用环境变量 XUEQIU_TOKEN")
    parser.add_argument("--cookies", default="", help="浏览器整段 Cookie；也可用环境变量 XUEQIU_COOKIES")
    parser.add_argument("--max-pages", type=int, default=3, help="最多翻页，默认 3")
    parser.add_argument("--limit", type=int, default=10, help="打印前 N 条；0 为全部")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.token or args.cookies:
        set_token(args.token, args.cookies)
    start = args.start or None
    end = args.end or None
    code = args.code or args.stock

    if args.article:
        pack = fetch_article(args.article)
        if args.json:
            print_items(pack, 0, True)
        else:
            from company.news.xueqiu._common import cli_print

            if pack.get("error"):
                cli_print(f"error: {pack['error']}")
                return 1
            bits = [pack.get("published_at") or "", pack.get("media_name") or "", pack.get("title") or ""]
            cli_print("  ".join(b for b in bits if b))
            cli_print(pack.get("url") or "")
            content = pack.get("content") or ""
            cli_print(content if args.limit <= 0 else content[: max(200, args.limit * 80)])
        return 1 if pack.get("error") else 0

    if args.search:
        pack = search_posts(
            args.search,
            symbol=code,
            source=args.source or "all",
            sort=args.sort,
            start=start,
            end=end,
            days=args.days,
            max_pages=args.max_pages,
            strict=args.strict,
        )
        print_items(pack, args.limit, args.json)
        return 1 if pack.get("error") else 0

    if args.flash:
        pack = fetch_flash(
            code=code,
            max_pages=args.max_pages,
            since_id=args.since_id,
            start=start,
            end=end,
            days=args.days,
        )
        print_items(pack, args.limit, args.json)
        return 1 if pack.get("error") else 0

    if args.column:
        pack = fetch_column_news(
            args.column,
            start=start,
            end=end,
            days=args.days,
            max_pages=args.max_pages,
        )
        print_items(pack, args.limit, args.json)
        return 1 if pack.get("error") else 0

    if not code:
        parser.error("请提供股票代码，或使用 --flash / --column / --article / --search")

    if args.all:
        pack = fetch_company(
            code,
            start=start,
            end=end,
            days=args.days if args.days is not None else 31,
            max_pages=args.max_pages,
            strict=args.strict,
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
                    "items": (pack.get("news") or {}).get("items") or [],
                    "channel": "news",
                    "count": (pack.get("news") or {}).get("count") or 0,
                    "total": (pack.get("news") or {}).get("total") or 0,
                },
                args.limit,
                False,
            )
            print_items(pack.get("notices") or {}, args.limit, False)
            print_items(pack.get("reports") or {}, args.limit, False)
        return 1 if pack.get("error") else 0

    if args.reports:
        pack = fetch_reports(
            code,
            start=start,
            end=end,
            days=args.days,
            max_pages=args.max_pages,
            strict=args.strict,
        )
        print_items(pack, args.limit, args.json)
        return 1 if pack.get("error") else 0

    if args.notices:
        pack = fetch_notices(
            code,
            start=start,
            end=end,
            days=args.days if args.days is not None else 365,
            max_pages=args.max_pages,
            strict=args.strict,
        )
        print_items(pack, args.limit, args.json)
        return 1 if pack.get("error") else 0

    if args.discuss or args.trans or args.source:
        src = args.source or ("trans" if args.trans else "user")
        pack = fetch_discuss(
            code,
            source=src,
            sort=args.sort,
            start=start,
            end=end,
            days=args.days if args.days is not None else 7,
            max_pages=args.max_pages,
            strict=args.strict,
        )
        print_items(pack, args.limit, args.json)
        return 1 if pack.get("error") else 0

    pack = fetch_news(
        code,
        start=start,
        end=end,
        days=args.days if args.days is not None else 31,
        max_pages=args.max_pages,
        strict=args.strict,
    )
    print_items(pack, args.limit, args.json)
    return 1 if pack.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
