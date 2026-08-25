"""同花顺个股公告：F10「公告列表」。

个股资讯页：https://basic.10jqka.com.cn/600519/news.html

    GET https://basic.10jqka.com.cn/basicapi/notice/pub
    - type      stock
    - code      六位代码
    - market    沪 17 / 深 33 / 北交所 151 或 145
    - classify  all / eq-f1001 业绩 / eq-f1002 重大事项 / eq-f1003 股份变动 / eq-f1004 决议
    - page      页码，从 1 起（不是 current）
    - limit     每页条数

``raw_url`` 是交易所 PDF。这是同花顺转载的监管披露，一手请走巨潮 / 交易所。
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

from company.news.tonghuashun._common import (
    F10_HOST,
    PUB_API,
    REQUEST_PAUSE_SEC,
    SOURCE,
    date_range,
    decode_html,
    dedupe,
    empty_pack,
    f10_news_url,
    fmt_dt,
    get_payload,
    headers_for,
    in_range,
    map_choice,
    oldest_day,
    resolve_keyword,
    ths_market,
)

logger = logging.getLogger(__name__)

PAGE_SIZE = 15
MAX_PAGES = 50

CLASSIFIES: dict[str, str] = {
    "all": "all",
    "全部": "all",
    "全部公告": "all",
    "earnings": "eq-f1001",
    "业绩": "eq-f1001",
    "业绩公告": "eq-f1001",
    "eq-f1001": "eq-f1001",
    "major": "eq-f1002",
    "重大": "eq-f1002",
    "重大事项": "eq-f1002",
    "eq-f1002": "eq-f1002",
    "share": "eq-f1003",
    "股份": "eq-f1003",
    "股份变动": "eq-f1003",
    "股份变动公告": "eq-f1003",
    "eq-f1003": "eq-f1003",
    "resolution": "eq-f1004",
    "决议": "eq-f1004",
    "决议公告": "eq-f1004",
    "eq-f1004": "eq-f1004",
}
CLASSIFY_LABELS: dict[str, str] = {
    "all": "全部公告",
    "eq-f1001": "业绩公告",
    "eq-f1002": "重大事项",
    "eq-f1003": "股份变动公告",
    "eq-f1004": "决议公告",
}

_MARKET_FALLBACKS = ("17", "33", "151", "145")


def resolve_classify(classify: str | None) -> str:
    return map_choice(classify, CLASSIFIES, "all", "classify")


def _market_from_html(code: str) -> str:
    try:
        from core.http import browser_get

        resp = browser_get(
            f10_news_url(code),
            headers=headers_for(F10_HOST + "/"),
            timeout=20,
        )
        resp.raise_for_status()
        html = decode_html(resp)
    except Exception as exc:  # noqa: BLE001
        logger.info("读取 F10 marketId 失败 %s: %s", code, exc)
        return ""
    m = re.search(r'id=["\']marketId["\'][^>]*value=["\'](\d+)["\']', html)
    if not m:
        m = re.search(r'id=["\']marketId["\'][^>]*value=["\'](\d+)["\']', html.replace(" ", ""))
    return m.group(1) if m else ""


def query_page(
    code: str,
    *,
    page: int = 1,
    page_size: int = PAGE_SIZE,
    classify: str = "all",
    market: str = "",
) -> dict[str, Any]:
    """个股公告单页原始 JSON。``classify`` / ``market`` / ``page`` 都不能缺。"""
    stock = normalize_code(code) or safe_str(code)
    mid = safe_str(market) or ths_market(stock)
    payload = get_payload(
        PUB_API,
        params={
            "type": "stock",
            "code": stock,
            "market": mid,
            "classify": classify or "all",
            "page": max(1, int(page)),
            "limit": max(1, min(int(page_size), 50)),
        },
        headers=headers_for(f10_news_url(stock)),
        timeout=20,
    )
    return payload if isinstance(payload, dict) else {}


def _normalize_row(
    row: dict[str, Any],
    *,
    code: str = "",
    name: str = "",
    classify: str = "",
) -> dict[str, Any] | None:
    title = safe_str(row.get("title"))
    seq = safe_str(row.get("seq") or row.get("guid"))
    if not title:
        return None
    url = safe_str(row.get("pc_url") or row.get("mobile_url"))
    if url.startswith("http://"):
        url = "https://" + url[len("http://") :]
    pdf = safe_str(row.get("raw_url"))
    return {
        "code": code,
        "name": name,
        "article_id": seq,
        "seq": safe_str(row.get("seq")),
        "guid": safe_str(row.get("guid")),
        "title": title,
        "summary": "",
        "published_at": fmt_dt(row.get("time") or row.get("date")),
        "url": url,
        "mobile_url": safe_str(row.get("mobile_url")),
        "pdf_url": pdf,
        "source": SOURCE,
        "channel": "notice",
        "category": CLASSIFY_LABELS.get(classify, classify) if classify and classify != "all" else "",
    }


def _ok(payload: dict[str, Any]) -> bool:
    status = payload.get("status_code")
    return status in (0, "0")


def fetch_notices(
    code_or_name: str,
    *,
    start: str | date | datetime | None = None,
    end: str | date | datetime | None = None,
    days: int | None = 365,
    max_pages: int = 5,
    page_size: int = PAGE_SIZE,
    classify: str | None = "all",
    market: str = "",
) -> dict[str, Any]:
    """按股票拉 F10 公告列表。"""
    resolved = resolve_keyword(code_or_name)
    code = resolved["code"] or normalize_code(code_or_name)
    name = resolved["name"]
    page_url = f10_news_url(code)
    if not code:
        return empty_pack(
            code=code,
            name=name,
            keyword=resolved["keyword"],
            channel="notice",
            error="缺少股票代码",
            page=page_url,
        )

    api_classify = resolve_classify(classify)
    mid = safe_str(market) or resolved.get("market") or ths_market(code)
    start_d, end_d = date_range(start, end, days)
    size = max(1, min(int(page_size), 50))
    limit = max(1, int(max_pages))

    def _pull(use_market: str) -> tuple[dict[str, Any], list[dict[str, Any]], int, list[dict[str, Any]]]:
        items: list[dict[str, Any]] = []
        types: list[dict[str, Any]] = []
        total = 0
        total_pages = 1
        page = 1
        last_payload: dict[str, Any] = {}
        while page <= total_pages and page <= limit:
            payload = query_page(
                code,
                page=page,
                page_size=size,
                classify=api_classify,
                market=use_market,
            )
            last_payload = payload
            if not _ok(payload):
                if page == 1:
                    return payload, items, total, types
                break
            data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
            rows = data.get("data") or []
            if data.get("type") and not types:
                raw_types = data.get("type") or []
                if isinstance(raw_types, list):
                    types = [x for x in raw_types if isinstance(x, dict)]
            total = int(data.get("total") or total)
            if total:
                total_pages = max(1, (total + size - 1) // size)
            if not isinstance(rows, list) or not rows:
                break
            page_items: list[dict[str, Any]] = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                item = _normalize_row(row, code=code, name=name, classify=api_classify)
                if not item:
                    continue
                if in_range(item, start_d, end_d):
                    items.append(item)
                page_items.append(item)
            if start_d:
                old = oldest_day(page_items)
                if old and old < start_d:
                    break
            if page >= total_pages or len(rows) < size:
                break
            page += 1
            if page <= total_pages and page <= limit:
                time.sleep(REQUEST_PAUSE_SEC)
        return last_payload, items, total, types

    try:
        payload, items, total, types = _pull(mid)
    except Exception as exc:  # noqa: BLE001
        logger.warning("同花顺公告失败: %s", exc)
        return empty_pack(
            code=code,
            name=name,
            keyword=resolved["keyword"],
            channel="notice",
            error=str(exc),
            page=page_url,
            classify=api_classify,
            market=mid,
            begin_date=start_d.isoformat() if start_d else "",
            end_date=end_d.isoformat() if end_d else "",
        )

    data_block = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    if not _ok(payload) or (not items and int(data_block.get("total") or 0) == 0):
        html_mid = _market_from_html(code)
        tried = {mid}
        candidates = [html_mid] + [x for x in _MARKET_FALLBACKS if x]
        for alt in candidates:
            if not alt or alt in tried:
                continue
            tried.add(alt)
            try:
                payload, items, total, types = _pull(alt)
            except Exception as exc:  # noqa: BLE001
                logger.info("同花顺公告改 market=%s 失败: %s", alt, exc)
                continue
            if _ok(payload):
                mid = alt
                break

    if not _ok(payload) and not items:
        msg = safe_str(payload.get("status_msg")) or f"status_code={payload.get('status_code')}"
        return empty_pack(
            code=code,
            name=name,
            keyword=resolved["keyword"],
            channel="notice",
            error=msg,
            page=page_url,
            classify=api_classify,
            market=mid,
            begin_date=start_d.isoformat() if start_d else "",
            end_date=end_d.isoformat() if end_d else "",
        )

    items = dedupe(items)
    return {
        "code": code,
        "name": name,
        "keyword": resolved["keyword"],
        "classify": api_classify,
        "market": mid,
        "types": types,
        "begin_date": start_d.isoformat() if start_d else "",
        "end_date": end_d.isoformat() if end_d else "",
        "source": SOURCE,
        "channel": "notice",
        "count": len(items),
        "total": total or len(items),
        "items": items,
        "page": page_url,
    }


def _pdf_referer(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if "sse.com.cn" in host:
        return "https://www.sse.com.cn/"
    if "szse.cn" in host:
        return "https://www.szse.cn/"
    if "bse.cn" in host or "bjse" in host:
        return "https://www.bse.cn/"
    return f10_news_url("")


def download_pdf(url: str, dest: str | Path) -> Path:
    dest_path = Path(dest)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    data = get_bytes(
        url,
        headers={"Referer": _pdf_referer(url)},
        timeout=60,
    )
    dest_path.write_bytes(data)
    return dest_path


def _safe_filename(title: str, seq: str, url: str) -> str:
    stem = Path(unquote(urlparse(url).path)).name or f"{seq}.pdf"
    if not title:
        return stem
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", title).strip(" .")
    cleaned = cleaned[:80] or seq or "notice"
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
    """批量下载列表里的 ``pdf_url``。"""
    folder = Path(dest_dir)
    folder.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    for i, item in enumerate(items):
        if limit > 0 and i >= limit:
            break
        url = safe_str(item.get("pdf_url"))
        if not url:
            continue
        name = _safe_filename(safe_str(item.get("title")), safe_str(item.get("seq")), url)
        path = download_pdf(url, folder / name)
        saved.append(path)
        time.sleep(REQUEST_PAUSE_SEC)
    return saved
