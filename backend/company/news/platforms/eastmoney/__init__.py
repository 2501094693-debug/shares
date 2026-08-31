"""东方财富新闻：搜索、7×24 快讯、栏目、F10 资讯公告、公告附件、正文。

东财没有文档化的公开新闻 API，以下全部是官网前端 XHR。

    python -m company.news.platforms.eastmoney 600519
    python -m company.news.platforms.eastmoney 贵州茅台 --days 7 --strict
    python -m company.news.platforms.eastmoney 600519 --f10
    python -m company.news.platforms.eastmoney 600519 --notices --days 90
    python -m company.news.platforms.eastmoney 600519 --notices --download ./pdfs --limit 3
    python -m company.news.platforms.eastmoney --flash
    python -m company.news.platforms.eastmoney --flash --column listed --stock 600519
    python -m company.news.platforms.eastmoney --column breakfast
    python -m company.news.platforms.eastmoney --article 202608243851623734
    python -m company.news.platforms.eastmoney 600519 --all --json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime
from typing import Any

from company.news.platforms.eastmoney.article import fetch_article
from company.news.platforms.eastmoney.columns import (
    COLUMNS as NEWS_COLUMNS,
    column_page_url,
    fetch_column_news,
    query_page as query_column_page,
    resolve_column as resolve_news_column,
)
from company.news.platforms.eastmoney.f10 import (
    fetch_f10,
    fetch_f10_news,
    fetch_f10_notices,
    query_page as query_f10_page,
)
from company.news.platforms.eastmoney.flash import (
    COLUMNS as FLASH_COLUMNS,
    fetch_flash,
    query_count as query_flash_count,
    query_page as query_flash_page,
    resolve_column as resolve_flash_column,
)
from company.news.platforms.eastmoney.notices import (
    download_notices,
    download_pdf as download_notice_pdf,
    fetch_notice_content,
    fetch_notices,
    query_content as query_notice_content,
    query_page as query_notice_page,
    stock_notices_url,
)
from company.news.platforms.eastmoney.search import (
    SCOPES,
    SORTS,
    TYPES,
    fetch_news,
    query_page,
    resolve_keyword,
    resolve_scope,
    resolve_sort,
    resolve_type,
    search_news,
    search_page_url,
)
from company.news.platforms.eastmoney._common import (
    SOURCE,
    article_url,
    f10_page_url,
    notice_page_url,
    print_items,
)

__all__ = [
    "FLASH_COLUMNS",
    "NEWS_COLUMNS",
    "SCOPES",
    "SORTS",
    "SOURCE",
    "TYPES",
    "article_url",
    "column_page_url",
    "download_notice_pdf",
    "download_notices",
    "f10_page_url",
    "fetch_article",
    "fetch_column_news",
    "fetch_company",
    "fetch_f10",
    "fetch_f10_news",
    "fetch_f10_notices",
    "fetch_flash",
    "fetch_news",
    "fetch_notice_content",
    "fetch_notices",
    "notice_page_url",
    "query_column_page",
    "query_f10_page",
    "query_flash_count",
    "query_flash_page",
    "query_notice_content",
    "query_notice_page",
    "query_page",
    "resolve_flash_column",
    "resolve_keyword",
    "resolve_news_column",
    "resolve_scope",
    "resolve_sort",
    "resolve_type",
    "search_news",
    "search_page_url",
    "stock_notices_url",
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
    """个股一次拉齐：搜索新闻 + F10 快照 + 公告列表。"""
    news = fetch_news(
        code_or_name,
        start=start,
        end=end,
        days=days,
        max_pages=max_pages,
        strict=strict,
    )
    f10 = fetch_f10(code_or_name, start=start, end=end, days=days)
    notices = fetch_notices(
        code_or_name,
        start=start,
        end=end,
        days=days if days is not None else 365,
        max_pages=max_pages,
    )
    code = news.get("code") or f10.get("code") or notices.get("code") or ""
    name = news.get("name") or f10.get("name") or notices.get("name") or ""
    return {
        "code": code,
        "name": name,
        "keyword": news.get("keyword") or "",
        "source": SOURCE,
        "channel": "company",
        "news": news,
        "f10": f10,
        "notices": notices,
        "count": int(news.get("count") or 0)
        + int(f10.get("news_count") or 0)
        + int(notices.get("count") or 0),
        "items": (news.get("items") or [])
        + (f10.get("news") or [])
        + (notices.get("items") or []),
        "page": search_page_url(str(news.get("keyword") or code_or_name)),
        "error": news.get("error") or f10.get("error") or notices.get("error") or "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="东方财富新闻接口：搜索 / 快讯 / 栏目 / F10 / 公告 / 正文")
    parser.add_argument(
        "code",
        nargs="?",
        default="",
        help="股票代码或公司简称；--flash / --column / --article 时可省略",
    )
    parser.add_argument("--days", type=int, default=None, help="回溯天数；搜索默认 31，公告默认 365")
    parser.add_argument("--start", default="", help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end", default="", help="结束日期 YYYY-MM-DD")
    parser.add_argument("--keyword", default="", help="覆盖自动解析出的检索词")
    parser.add_argument("--sort", default="time", help="搜索排序：time / relevance")
    parser.add_argument("--scope", default="default", help="搜索范围：default / global")
    parser.add_argument("--type", dest="kind", default="old", help="搜索类型：old / web / all")
    parser.add_argument("--strict", action="store_true", help="标题或摘要必须命中简称/代码")
    parser.add_argument("--flash", action="store_true", help="7×24 快讯")
    parser.add_argument(
        "--column",
        default="",
        help="栏目：breakfast / 1207，或快讯频道 focus/listed/...（与 --flash 连用）",
    )
    parser.add_argument("--stock", default="", help="快讯按 stockList 过滤的股票代码")
    parser.add_argument("--since-sort", default="", help="快讯增量水位 realSort")
    parser.add_argument("--f10", action="store_true", help="F10 资讯公告快照")
    parser.add_argument("--notices", action="store_true", help="东财公告列表")
    parser.add_argument("--article", default="", help="文章 ID 或 URL，拉正文")
    parser.add_argument("--all", action="store_true", help="搜索 + F10 + 公告")
    parser.add_argument("--max-pages", type=int, default=3, help="最多翻页，默认 3")
    parser.add_argument("--limit", type=int, default=10, help="打印/下载前 N 条；0 为全部")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    parser.add_argument("--download", default="", help="公告 PDF 保存目录（配合 --notices）")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    start = args.start or None
    end = args.end or None
    code = args.code or args.stock

    if args.article:
        pack = fetch_article(args.article)
        if args.json:
            print_items(pack, 0, True)
        else:
            from company.news.platforms.eastmoney._common import cli_print

            if pack.get("error"):
                cli_print(f"error: {pack['error']}")
                return 1
            bits = [pack.get("published_at") or "", pack.get("media_name") or "", pack.get("title") or ""]
            cli_print("  ".join(b for b in bits if b))
            cli_print(pack.get("url") or "")
            content = pack.get("content") or ""
            cli_print(content if args.limit <= 0 else content[: max(200, args.limit * 80)])
        return 1 if pack.get("error") else 0

    if args.flash:
        pack = fetch_flash(
            column=args.column or "global",
            code=code,
            max_pages=args.max_pages,
            since_sort=args.since_sort,
            start=start,
            end=end,
            days=args.days,
        )
        print_items(pack, args.limit, args.json)
        return 1 if pack.get("error") else 0

    if args.column and not args.notices and not args.f10 and not args.all:
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
        parser.error("请提供股票代码，或使用 --flash / --column / --article")

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
                    "channel": "search",
                    "count": (pack.get("news") or {}).get("count") or 0,
                    "total": (pack.get("news") or {}).get("total") or 0,
                },
                args.limit,
                False,
            )
            f10 = pack.get("f10") or {}
            print_items(
                {**f10, "items": f10.get("news") or [], "channel": "f10_news"},
                args.limit,
                False,
            )
            print_items(pack.get("notices") or {}, args.limit, False)
        return 1 if pack.get("error") else 0

    if args.f10:
        pack = fetch_f10(code, start=start, end=end, days=args.days)
        print_items(pack, args.limit, args.json)
        return 1 if pack.get("error") else 0

    if args.notices:
        pack = fetch_notices(
            code,
            start=start,
            end=end,
            days=args.days if args.days is not None else 365,
            max_pages=args.max_pages,
        )
        print_items(pack, args.limit, args.json)
        if args.download:
            saved = download_notices(
                pack.get("items") or [],
                args.download,
                limit=args.limit,
            )
            print(f"downloaded {len(saved)} files -> {args.download}")
        return 1 if pack.get("error") else 0

    pack = fetch_news(
        code,
        start=start,
        end=end,
        days=args.days if args.days is not None else 31,
        sort=args.sort,
        scope=args.scope,
        kind=args.kind,
        keyword=args.keyword,
        max_pages=args.max_pages,
        strict=args.strict,
    )
    print_items(pack, args.limit, args.json)
    return 1 if pack.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
