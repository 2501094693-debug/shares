"""同花顺新闻：个股热点新闻、公告、研报、7×24 快讯、正文。

同花顺没有文档化的公开新闻 API，以下全部是官网 F10 / 快讯页前端 XHR。
个股请走 F10；``tapp/news/push/stock`` 是全市场快讯，不能按代码检索。

    python -m company.news.tonghuashun 600519
    python -m company.news.tonghuashun 贵州茅台 --days 7
    python -m company.news.tonghuashun 600519 --notices --days 90
    python -m company.news.tonghuashun 600519 --notices --classify earnings --limit 5
    python -m company.news.tonghuashun 600519 --notices --download ./pdfs --limit 3
    python -m company.news.tonghuashun 600519 --reports
    python -m company.news.tonghuashun --flash
    python -m company.news.tonghuashun --flash --stock 600519
    python -m company.news.tonghuashun --article 679277455
    python -m company.news.tonghuashun --article https://stock.10jqka.com.cn/20260825/c679277455.shtml
    python -m company.news.tonghuashun 600519 --all --json
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import date, datetime
from typing import Any

from company.news.tonghuashun.article import fetch_article
from company.news.tonghuashun.flash import fetch_flash, query_page as query_flash_page
from company.news.tonghuashun.news import fetch_news, query_page, search_news
from company.news.tonghuashun.notices import (
    CLASSIFIES,
    CLASSIFY_LABELS,
    download_notices,
    download_pdf,
    fetch_notices,
    query_page as query_notice_page,
    resolve_classify,
)
from company.news.tonghuashun.reports import fetch_reports, query_page as query_report_page
from company.news.tonghuashun._common import (
    SOURCE,
    article_url,
    f10_news_url,
    print_items,
    resolve_keyword,
    search_page_url,
    ths_market,
)

__all__ = [
    "CLASSIFIES",
    "CLASSIFY_LABELS",
    "SOURCE",
    "article_url",
    "download_notices",
    "download_pdf",
    "f10_news_url",
    "fetch_article",
    "fetch_company",
    "fetch_flash",
    "fetch_news",
    "fetch_notices",
    "fetch_reports",
    "query_flash_page",
    "query_notice_page",
    "query_page",
    "query_report_page",
    "resolve_classify",
    "resolve_keyword",
    "search_news",
    "search_page_url",
    "ths_market",
]


def fetch_company(
    code_or_name: str,
    *,
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = 31,
    max_pages: int = 3,
    strict: bool = False,
    classify: str | None = "all",
) -> dict[str, Any]:
    """个股一次拉齐：热点新闻 + 公告 + 研报。"""
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
        classify=classify,
    )
    reports = fetch_reports(
        code_or_name,
        start=start,
        end=end,
        days=days,
    )
    code = news.get("code") or notices.get("code") or reports.get("code") or ""
    name = news.get("name") or notices.get("name") or reports.get("name") or ""
    return {
        "code": code,
        "name": name,
        "keyword": news.get("keyword") or notices.get("keyword") or "",
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
        "page": f10_news_url(str(code or code_or_name)),
        "error": news.get("error") or notices.get("error") or reports.get("error") or "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="同花顺新闻接口：个股新闻 / 公告 / 研报 / 快讯 / 正文")
    parser.add_argument(
        "code",
        nargs="?",
        default="",
        help="股票代码或公司简称；--flash / --article 时可省略",
    )
    parser.add_argument("--days", type=int, default=None, help="回溯天数；新闻默认 31，公告默认 365")
    parser.add_argument("--start", default="", help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end", default="", help="结束日期 YYYY-MM-DD")
    parser.add_argument("--strict", action="store_true", help="标题或摘要必须命中简称/代码")
    parser.add_argument("--flash", action="store_true", help="7×24 全市场快讯")
    parser.add_argument("--stock", default="", help="快讯事后按关联股票过滤")
    parser.add_argument("--since-ctime", default="", help="快讯增量水位 ctime（Unix 秒）")
    parser.add_argument("--since-id", default="", help="快讯增量水位 id")
    parser.add_argument("--notices", action="store_true", help="F10 公告列表")
    parser.add_argument(
        "--classify",
        default="all",
        help="公告分类：all / earnings / major / share / resolution",
    )
    parser.add_argument("--market", default="", help="覆盖自动推断的 F10 market 号")
    parser.add_argument("--reports", action="store_true", help="F10 研报列表")
    parser.add_argument("--article", default="", help="文章 seq 或 URL，拉正文")
    parser.add_argument("--all", action="store_true", help="新闻 + 公告 + 研报")
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
            from company.news.tonghuashun._common import cli_print

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
            code=code,
            max_pages=args.max_pages,
            since_ctime=args.since_ctime,
            since_id=args.since_id,
            start=start,
            end=end,
            days=args.days,
        )
        print_items(pack, args.limit, args.json)
        return 1 if pack.get("error") else 0

    if not code:
        parser.error("请提供股票代码，或使用 --flash / --article")

    if args.all:
        pack = fetch_company(
            code,
            start=start,
            end=end,
            days=args.days if args.days is not None else 31,
            max_pages=args.max_pages,
            strict=args.strict,
            classify=args.classify,
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
        pack = fetch_reports(code, start=start, end=end, days=args.days)
        print_items(pack, args.limit, args.json)
        return 1 if pack.get("error") else 0

    if args.notices:
        pack = fetch_notices(
            code,
            start=start,
            end=end,
            days=args.days if args.days is not None else 365,
            max_pages=args.max_pages,
            classify=args.classify,
            market=args.market,
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
        max_pages=args.max_pages,
        strict=args.strict,
    )
    print_items(pack, args.limit, args.json)
    return 1 if pack.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
