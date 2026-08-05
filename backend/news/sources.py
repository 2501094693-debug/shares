"""三类外部数据源：公司公告、媒体新闻、机构研报。

每条结果统一成字典，字段大致为：
  title / summary / source / url / published_at / kind / why
"""

from __future__ import annotations

import json
import math
import time
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import quote

import akshare as ak
import requests

from .constants import (
    EM_NEWS_CB,
    EM_NEWS_URL,
    EM_REPORT_URL,
    LOOKBACK_YEARS,
    NEWS_MAX_PAGES,
    NEWS_PAGE_SIZE,
    REQUEST_PAUSE_SEC,
)
from .utils import parse_time, safe_str, strip_em_tags, within_lookback

# curl_cffi 可伪装成 Chrome，东方财富搜索接口对普通 requests 经常拦截
try:
    from curl_cffi import requests as curl_requests
except ImportError:  # pragma: no cover
    curl_requests = None


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


def http_get(
    url: str,
    *,
    params: dict[str, Any],
    headers: dict[str, str],
    timeout: int = 25,
):
    """GET 请求：优先 curl_cffi（Chrome 指纹），否则退回 requests。"""
    if curl_requests is not None:
        return curl_requests.get(
            url,
            params=params,
            headers=headers,
            timeout=timeout,
            impersonate="chrome",
        )
    return requests.get(url, params=params, headers=headers, timeout=timeout)


# ---------------------------------------------------------------------------
# 1) 公司公告（akshare）
# ---------------------------------------------------------------------------


def fetch_notices(code: str, start: datetime | None = None) -> list[dict[str, Any]]:
    """拉取个股公告；start 为空时默认回溯 LOOKBACK_YEARS 年。"""
    end = date.today()
    if start is None:
        begin = (datetime.now() - timedelta(days=365 * LOOKBACK_YEARS)).date()
    else:
        begin = start.date() if isinstance(start, datetime) else start
    # akshare 该接口要求 YYYYMMDD
    begin_s = begin.strftime("%Y%m%d")
    end_s = end.strftime("%Y%m%d")

    try:
        df = ak.stock_individual_notice_report(
            security=code,
            symbol="全部",
            begin_date=begin_s,
            end_date=end_s,
        )
    except Exception:  # noqa: BLE001
        return []

    if df is None or df.empty:
        return []

    items: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        title = safe_str(row.get("公告标题"))
        if not title:
            continue
        notice_type = safe_str(row.get("公告类型"))
        items.append(
            {
                "title": title,
                "summary": notice_type,
                "source": "公司公告",
                "url": safe_str(row.get("网址")),
                "published_at": safe_str(row.get("公告日期")),
                "kind": "notice",
                "why": notice_type or "公告",
            }
        )
    return items


# ---------------------------------------------------------------------------
# 2) 媒体新闻（东方财富搜索 JSONP）
# ---------------------------------------------------------------------------


def fetch_em_news_page(keyword: str, page_index: int) -> tuple[int, list[dict[str, Any]]]:
    """请求东方财富新闻搜索的一页，返回 (命中总数, 本页列表)。"""
    inner = {
        "uid": "",
        "keyword": keyword,
        "type": ["cmsArticleWebOld"],
        "client": "web",
        "clientType": "web",
        "clientVersion": "curr",
        "param": {
            "cmsArticleWebOld": {
                "searchScope": "default",
                "sort": "time",
                "pageIndex": page_index,
                "pageSize": NEWS_PAGE_SIZE,
                "preTag": "<em>",
                "postTag": "</em>",
            }
        },
    }
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": f"https://so.eastmoney.com/news/s?keyword={quote(keyword)}",
        "Accept": "*/*",
    }

    try:
        resp = http_get(
            EM_NEWS_URL,
            params={
                "cb": EM_NEWS_CB,
                "param": json.dumps(inner, ensure_ascii=False),
                "_": str(int(time.time() * 1000)),
            },
            headers=headers,
            timeout=25,
        )
        resp.raise_for_status()
        text = resp.text
        # 响应是 JSONP：callback({...})
        start = text.find("(")
        end = text.rfind(")")
        if start < 0 or end <= start:
            return 0, []
        payload = json.loads(text[start + 1 : end])
    except Exception:  # noqa: BLE001
        return 0, []

    hits = int(payload.get("hitsTotal") or 0)
    rows = ((payload.get("result") or {}).get("cmsArticleWebOld")) or []
    # 兼容 list 或 {list/data: [...]} 两种结构
    if isinstance(rows, dict):
        rows = rows.get("list") or rows.get("data") or []
    if not isinstance(rows, list):
        rows = []

    items: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = strip_em_tags(safe_str(row.get("title")))
        if not title:
            continue
        code_id = safe_str(row.get("code"))
        url = safe_str(row.get("url"))
        if not url and code_id:
            url = f"http://finance.eastmoney.com/a/{code_id}.html"
        items.append(
            {
                "title": title,
                "summary": strip_em_tags(safe_str(row.get("content"))),
                "source": safe_str(row.get("mediaName")) or "东方财富",
                "url": url,
                "published_at": safe_str(row.get("date")),
                "kind": "news",
                "why": "",
            }
        )
    return hits, items


def fetch_media_news(keyword: str, start: datetime) -> list[dict[str, Any]]:
    """按关键词分页拉取媒体新闻，直到超出回溯窗口或没有下一页。"""
    keyword = (keyword or "").strip()
    if not keyword:
        return []

    hits, first = fetch_em_news_page(keyword, 1)
    collected = list(first)
    total_pages = (
        min(NEWS_MAX_PAGES, max(1, math.ceil(hits / NEWS_PAGE_SIZE)))
        if hits
        else NEWS_MAX_PAGES
    )

    for page in range(2, total_pages + 1):
        # 已收集到的最旧一条若已早于窗口，不必再翻页
        if collected:
            dated = [parse_time(x.get("published_at")) for x in collected]
            dated = [d for d in dated if d is not None]
            if dated and min(dated) < start:
                break

        time.sleep(REQUEST_PAUSE_SEC)
        _, rows = fetch_em_news_page(keyword, page)
        if not rows:
            break
        collected.extend(rows)

        page_dates = [parse_time(x.get("published_at")) for x in rows]
        page_dates = [d for d in page_dates if d is not None]
        if page_dates and min(page_dates) < start:
            break

    return [x for x in collected if within_lookback(x, start)]


# ---------------------------------------------------------------------------
# 3) 机构研报（东方财富 API，失败则 akshare 兜底）
# ---------------------------------------------------------------------------


def fetch_research_reports(code: str, start: datetime) -> list[dict[str, Any]]:
    """拉取个股回溯窗口内的机构研报。"""
    code = (code or "").strip()
    if not code:
        return []

    begin = start.date().strftime("%Y-%m-%d")
    # endTime 略放宽到下一年初，避免边界漏数
    end = (date.today().replace(year=date.today().year + 1)).strftime("%Y-01-01")
    page_size = 100
    page_no = 1
    total_pages = 1
    items: list[dict[str, Any]] = []

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://data.eastmoney.com/report/stock.jshtml",
        "Accept": "application/json, text/plain, */*",
    }

    while page_no <= total_pages and page_no <= 50:
        params = {
            "industryCode": "*",
            "pageSize": str(page_size),
            "industry": "*",
            "rating": "*",
            "ratingChange": "*",
            "beginTime": begin,
            "endTime": end,
            "pageNo": str(page_no),
            "fields": "",
            "qType": "0",
            "orgCode": "",
            "code": code,
            "rcode": "",
            "p": str(page_no),
            "pageNum": str(page_no),
            "pageNumber": str(page_no),
        }
        try:
            resp = http_get(EM_REPORT_URL, params=params, headers=headers, timeout=30)
            resp.raise_for_status()
            payload = resp.json()
        except Exception:  # noqa: BLE001
            break

        rows = payload.get("data") or []
        if not isinstance(rows, list) or not rows:
            break

        hits = int(payload.get("hits") or 0)
        total_pages = int(payload.get("TotalPage") or math.ceil(hits / page_size) or 1)

        for row in rows:
            if not isinstance(row, dict):
                continue
            title = safe_str(row.get("title"))
            if not title:
                continue
            org = safe_str(row.get("orgSName") or row.get("orgName"))
            rating = safe_str(row.get("emRatingName") or row.get("sRatingName"))
            info_code = safe_str(row.get("infoCode"))
            url = f"https://pdf.dfcfw.com/pdf/H3_{info_code}_1.pdf" if info_code else ""
            why_parts = [p for p in (org, rating) if p]
            items.append(
                {
                    "title": title,
                    "summary": " · ".join(why_parts) if why_parts else "机构研报",
                    "source": org or "机构研报",
                    "url": url,
                    "published_at": safe_str(row.get("publishDate")),
                    "kind": "report",
                    "why": rating or "研报",
                    "org": org,
                    "rating": rating,
                }
            )

        page_no += 1
        if page_no <= total_pages:
            time.sleep(REQUEST_PAUSE_SEC)

    if items:
        return [x for x in items if within_lookback(x, start)]

    # 直连 API 无数据时，用 akshare 兜底
    return _fetch_reports_via_akshare(code, start)


def _fetch_reports_via_akshare(code: str, start: datetime) -> list[dict[str, Any]]:
    """akshare 研报兜底。"""
    try:
        df = ak.stock_research_report_em(symbol=code)
    except Exception:  # noqa: BLE001
        return []
    if df is None or df.empty:
        return []

    fallback: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        title = safe_str(row.get("报告名称"))
        if not title:
            continue
        org = safe_str(row.get("机构"))
        rating = safe_str(row.get("东财评级"))
        why_parts = [p for p in (org, rating) if p]
        fallback.append(
            {
                "title": title,
                "summary": " · ".join(why_parts) if why_parts else "机构研报",
                "source": org or "机构研报",
                "url": safe_str(row.get("报告PDF链接")),
                "published_at": safe_str(row.get("日期")),
                "kind": "report",
                "why": rating or "研报",
                "org": org,
                "rating": rating,
            }
        )
    return [x for x in fallback if within_lookback(x, start)]
