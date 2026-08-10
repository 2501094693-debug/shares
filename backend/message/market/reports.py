"""东方财富机构研报（akshare 兜底）。"""

from __future__ import annotations

import math
import time
from datetime import date, datetime
from typing import Any

import akshare as ak

from message.disclosure.http_util import (
    http_get,
    safe_str,
    sleep_pause,
    within_lookback,
)

from .constants import EM_REPORT_URL, REQUEST_PAUSE_SEC


def fetch_research_reports(code: str, start: datetime) -> list[dict[str, Any]]:
    code = (code or "").strip()
    if not code:
        return []

    begin = start.date().strftime("%Y-%m-%d")
    end = (date.today().replace(year=date.today().year + 1)).strftime("%Y-01-01")
    page_size = 100
    page_no = 1
    total_pages = 1
    items: list[dict[str, Any]] = []

    headers = {
        "Referer": "https://data.eastmoney.com/report/stock.jshtml",
        "Accept": "application/json, text/plain, */*",
    }

    while page_no <= total_pages and page_no <= 200:
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
                    "channel": "report",
                    "why": rating or "研报",
                    "org": org,
                    "rating": rating,
                }
            )

        page_no += 1
        if page_no <= total_pages:
            sleep_pause(REQUEST_PAUSE_SEC)

    if items:
        return [x for x in items if within_lookback(x, start)]
    return _fetch_reports_via_akshare(code, start)


def _fetch_reports_via_akshare(code: str, start: datetime) -> list[dict[str, Any]]:
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
                "channel": "report",
                "why": rating or "研报",
                "org": org,
                "rating": rating,
            }
        )
    return [x for x in fallback if within_lookback(x, start)]
