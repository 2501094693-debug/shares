"""东财公告聚合：``np-anotice-stock`` 列表 + ``np-cnotice-stock`` 正文/附件。

列表页：https://data.eastmoney.com/notices/stock/600519.html

    GET https://np-anotice-stock.eastmoney.com/api/security/ann
    GET https://np-cnotice-stock.eastmoney.com/api/content/ann

公告 PDF 在 content 的 ``attach_list[].attach_url``。
这是东财转载的监管披露，不是媒体新闻；一手请走 ``company.news.official.cninfo`` / ``company.news.official.exchange``。
"""

from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urlparse

from core.codes import normalize_code, safe_str
from core.http import get_bytes

from company.news.platforms.eastmoney._common import (
    REQUEST_PAUSE_SEC,
    SOURCE,
    date_range,
    dedupe,
    empty_pack,
    fmt_dt,
    get_payload,
    headers_for,
    in_range,
    notice_page_url,
    resolve_keyword,
)

logger = logging.getLogger(__name__)

LIST_API = "https://np-anotice-stock.eastmoney.com/api/security/ann"
CONTENT_API = "https://np-cnotice-stock.eastmoney.com/api/content/ann"
PAGE_SIZE = 20
MAX_PAGES = 50


def stock_notices_url(code: str) -> str:
    c = normalize_code(code) or safe_str(code)
    if not c:
        return "https://data.eastmoney.com/notices/"
    return f"https://data.eastmoney.com/notices/stock/{c}.html"


def query_page(
    code: str,
    *,
    page: int = 1,
    page_size: int = PAGE_SIZE,
    ann_type: str = "A",
) -> dict[str, Any]:
    """个股公告单页。``ann_type=A`` 为 A 股公告。"""
    stock = normalize_code(code) or safe_str(code)
    payload = get_payload(
        LIST_API,
        params={
            "sr": "-1",
            "page_size": max(1, min(int(page_size), 50)),
            "page_index": max(1, int(page)),
            "ann_type": ann_type or "A",
            "client_source": "web",
            "stock_list": stock,
            "f_node": "0",
            "s_node": "0",
        },
        headers=headers_for(stock_notices_url(stock)),
        timeout=20,
    )
    return payload if isinstance(payload, dict) else {}


def query_content(art_code: str, *, page_index: int = 1) -> dict[str, Any]:
    """公告正文/附件。``page_index`` 必填。"""
    art = safe_str(art_code)
    payload = get_payload(
        CONTENT_API,
        params={
            "art_code": art,
            "client_source": "web",
            "page_index": max(1, int(page_index)),
        },
        headers=headers_for("https://data.eastmoney.com/notices/"),
        timeout=25,
    )
    return payload if isinstance(payload, dict) else {}


def _column_name(row: dict[str, Any]) -> str:
    cols = row.get("columns") or []
    if isinstance(cols, list) and cols and isinstance(cols[0], dict):
        return safe_str(cols[0].get("column_name"))
    return ""


def _stock_from_row(row: dict[str, Any], fallback: str) -> tuple[str, str]:
    codes = row.get("codes") or []
    if isinstance(codes, list) and codes and isinstance(codes[0], dict):
        return (
            normalize_code(safe_str(codes[0].get("stock_code"))) or fallback,
            safe_str(codes[0].get("short_name")),
        )
    return fallback, ""


def _normalize_row(
    row: dict[str, Any],
    *,
    code: str = "",
    name: str = "",
) -> dict[str, Any] | None:
    title = safe_str(row.get("title_ch") or row.get("title"))
    art = safe_str(row.get("art_code"))
    if not title:
        return None
    stock, short = _stock_from_row(row, code)
    return {
        "code": stock,
        "name": short or name,
        "art_code": art,
        "article_id": art,
        "title": title,
        "summary": "",
        "published_at": fmt_dt(row.get("display_time") or row.get("notice_date")),
        "notice_date": fmt_dt(row.get("notice_date")),
        "url": notice_page_url(stock, art),
        "source": SOURCE,
        "channel": "notice",
        "category": _column_name(row),
        "pdf_url": "",
    }


def fetch_notices(
    code_or_name: str,
    *,
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = 365,
    max_pages: int = 5,
    page_size: int = PAGE_SIZE,
    ann_type: str = "A",
) -> dict[str, Any]:
    """按股票拉东财公告列表。"""
    resolved = resolve_keyword(code_or_name)
    code = resolved["code"] or normalize_code(code_or_name)
    name = resolved["name"]
    page_url = stock_notices_url(code)
    if not code:
        return empty_pack(
            code=code,
            name=name,
            channel="notice",
            error="缺少股票代码",
            page=page_url,
        )

    start_d, end_d = date_range(start, end, days)
    items: list[dict[str, Any]] = []
    total = 0
    total_pages = 1
    page = 1
    limit = max(1, int(max_pages))
    while page <= total_pages and page <= limit:
        try:
            payload = query_page(code, page=page, page_size=page_size, ann_type=ann_type)
        except Exception as exc:  # noqa: BLE001
            logger.warning("东财公告失败 page=%s: %s", page, exc)
            if page == 1:
                return empty_pack(
                    code=code,
                    name=name,
                    channel="notice",
                    error=str(exc),
                    page=page_url,
                    begin_date=start_d.isoformat() if start_d else "",
                    end_date=end_d.isoformat() if end_d else "",
                )
            break
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        rows = data.get("list") or []
        total = int(data.get("total_hits") or total)
        if total:
            total_pages = max(1, (total + page_size - 1) // page_size)
        if not isinstance(rows, list) or not rows:
            break
        for row in rows:
            if not isinstance(row, dict):
                continue
            item = _normalize_row(row, code=code, name=name)
            if item and in_range(item, start_d, end_d):
                items.append(item)
        if page >= total_pages:
            break
        page += 1
        if page <= total_pages and page <= limit:
            time.sleep(REQUEST_PAUSE_SEC)

    items = dedupe(items)
    return {
        "code": code,
        "name": name,
        "keyword": resolved["keyword"],
        "ann_type": ann_type,
        "begin_date": start_d.isoformat() if start_d else "",
        "end_date": end_d.isoformat() if end_d else "",
        "source": SOURCE,
        "channel": "notice",
        "count": len(items),
        "total": total or len(items),
        "items": items,
        "page": page_url,
    }


def _first_pdf(data: dict[str, Any]) -> str:
    for key in ("attach_list", "attach_list_ch"):
        rows = data.get(key) or []
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            url = safe_str(row.get("attach_url"))
            if url.lower().endswith(".pdf") or ".pdf" in url.lower():
                return url.split("?")[0] if url.lower().endswith(".pdf") else url
            if url:
                return url
    return ""


def fetch_notice_content(art_code: str, *, code: str = "") -> dict[str, Any]:
    """单条公告正文与 PDF 附件。"""
    art = safe_str(art_code)
    if not art:
        return empty_pack(channel="notice", error="缺少 art_code")
    try:
        payload = query_content(art)
    except Exception as exc:  # noqa: BLE001
        logger.warning("东财公告正文失败 %s: %s", art, exc)
        return empty_pack(code=code, channel="notice", error=str(exc), art_code=art)

    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    if not data:
        return empty_pack(
            code=code,
            channel="notice",
            error=safe_str(payload.get("message")) or "无正文",
            art_code=art,
        )
    stock, short = _stock_from_row(data, code)
    pdf = _first_pdf(data)
    title = safe_str(data.get("title_ch") or data.get("title") or data.get("notice_title"))
    return {
        "code": stock,
        "name": short,
        "art_code": safe_str(data.get("art_code") or art),
        "title": title,
        "published_at": fmt_dt(data.get("display_time") or data.get("notice_date")),
        "notice_date": fmt_dt(data.get("notice_date")),
        "url": notice_page_url(stock, art),
        "pdf_url": pdf,
        "source": SOURCE,
        "channel": "notice",
        "category": _column_name(data),
        "attach_list": data.get("attach_list") or [],
        "content": data.get("content") or data.get("notice_content") or "",
    }


def download_pdf(url: str, dest: str | Path) -> Path:
    dest_path = Path(dest)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    data = get_bytes(
        url,
        headers={"Referer": "https://data.eastmoney.com/"},
        timeout=60,
    )
    dest_path.write_bytes(data)
    return dest_path


def _safe_filename(title: str, art_code: str, url: str) -> str:
    stem = Path(unquote(urlparse(url).path)).name or f"{art_code}.pdf"
    if not title:
        return stem
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", title).strip(" .")
    cleaned = cleaned[:80] or art_code or "notice"
    suffix = Path(stem).suffix or ".pdf"
    if "?" in suffix:
        suffix = ".pdf"
    return f"{cleaned}{suffix}"


def download_notices(
    items: Iterable[dict[str, Any]],
    dest_dir: str | Path,
    *,
    limit: int = 0,
) -> list[Path]:
    """批量下载列表里的 PDF；缺 ``pdf_url`` 时先打 content 接口。"""
    folder = Path(dest_dir)
    folder.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    for i, item in enumerate(items):
        if limit > 0 and i >= limit:
            break
        url = safe_str(item.get("pdf_url"))
        art = safe_str(item.get("art_code"))
        if not url and art:
            detail = fetch_notice_content(art, code=safe_str(item.get("code")))
            url = safe_str(detail.get("pdf_url"))
            time.sleep(REQUEST_PAUSE_SEC)
        if not url:
            continue
        name = _safe_filename(safe_str(item.get("title")), art, url)
        path = download_pdf(url, folder / name)
        saved.append(path)
        time.sleep(REQUEST_PAUSE_SEC)
    return saved
