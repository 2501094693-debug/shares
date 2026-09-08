"""请求数据：联想 orgId、翻页拉列表、下 PDF。只保存原始 JSON。"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Iterable

from core.codes import detect_market, normalize_code, safe_str
from core.http import browser_post, get_bytes, get_json
from core.paths import CNINFO_ORG_MAP_CACHE, ensure_cache_dirs
from company.news.official.cninfo.constants import (
    FORM_HEADERS,
    HEADERS,
    PAGE_SIZE,
    QUERY_URL,
    REQUEST_PAUSE_SEC,
    SEARCH_TIMEOUT_SEC,
    SEARCH_URL,
    STOCK_LIST_TIMEOUT_SEC,
    STOCK_LIST_URLS,
)
from company.news.official.cninfo.params import list_form
from company.news.official.cninfo.parse import parse_org_map, parse_orgs, safe_filename

logger = logging.getLogger(__name__)

_STOCK_MAP: dict[str, dict[str, str]] | None = None


def _post_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = SEARCH_TIMEOUT_SEC,
) -> Any:
    resp = browser_post(
        url,
        params=params,
        data=data,
        headers=headers or HEADERS,
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


def infer_org_from_code(code: str) -> dict[str, str] | None:
    """按代码号段推断 orgId，避免 topSearch 超时阻塞。

    已验证规则：
    - 沪市 60/90：gssh0{6位代码}，如 600990 → gssh0600990
    - 深市 00 开头：gssz{7位补零}，如 000001 → gssz0000001
    """
    stock = normalize_code(code)
    if not stock or len(stock) != 6:
        return None
    market = detect_market(stock)
    org_id = ""
    if market == "sse" and stock.startswith(("60", "90")):
        org_id = f"gssh0{stock}"
    elif market == "szse" and stock.startswith("00"):
        org_id = f"gssz{stock.zfill(7)}"
    if not org_id:
        return None
    return {
        "code": stock,
        "org_id": org_id,
        "name": "",
        "category": "",
    }


def _load_org_map_disk() -> dict[str, dict[str, str]]:
    path = CNINFO_ORG_MAP_CACHE
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.info("读取巨潮 org 缓存失败: %s", exc)
        return {}
    if not isinstance(payload, dict):
        return {}
    out: dict[str, dict[str, str]] = {}
    for key, row in payload.items():
        if not isinstance(row, dict):
            continue
        code = normalize_code(safe_str(row.get("code")) or safe_str(key))
        org_id = safe_str(row.get("org_id"))
        if code and org_id:
            out[code] = {
                "code": code,
                "org_id": org_id,
                "name": safe_str(row.get("name")),
                "category": safe_str(row.get("category")),
                "pinyin": safe_str(row.get("pinyin")),
            }
    return out


def _save_org_map_disk(mapping: dict[str, dict[str, str]]) -> None:
    if not mapping:
        return
    try:
        ensure_cache_dirs()
        CNINFO_ORG_MAP_CACHE.write_text(
            json.dumps(mapping, ensure_ascii=False, indent=0),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.info("写入巨潮 org 缓存失败: %s", exc)


def search_orgs(keyword: str, *, max_num: int = 10) -> list[dict[str, str]]:
    """topSearch 联想：代码或简称。超时快速失败，不阻塞主流程。"""
    text = safe_str(keyword)
    if not text:
        return []
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            rows = _post_json(
                SEARCH_URL,
                params={"keyWord": text, "maxNum": max(1, min(int(max_num), 50))},
                headers=HEADERS,
                timeout=SEARCH_TIMEOUT_SEC,
            )
            return parse_orgs(rows)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt == 0:
                time.sleep(0.5)
    logger.warning("topSearch 失败 keyword=%s: %s", text, last_exc)
    return []


def load_org_map(*, force: bool = False) -> dict[str, dict[str, str]]:
    """加载巨潮静态股票表（代码 → orgId）。先读本地缓存，再拉官网 JSON。"""
    global _STOCK_MAP
    if _STOCK_MAP is not None and not force:
        return _STOCK_MAP

    mapping = _load_org_map_disk()
    for url in STOCK_LIST_URLS:
        try:
            payload = get_json(url, timeout=STOCK_LIST_TIMEOUT_SEC, retries=0)
        except Exception as exc:  # noqa: BLE001
            logger.info("股票表不可用 %s: %s", url, exc)
            continue
        rows = payload.get("stockList") if isinstance(payload, dict) else payload
        mapping.update(parse_org_map(rows))

    _STOCK_MAP = mapping
    if mapping:
        _save_org_map_disk(mapping)
    return mapping


def query_page(
    *,
    stock: str = "",
    page_num: int = 1,
    page_size: int = PAGE_SIZE,
    column: str = "szse",
    tab: str = "fulltext",
    se_date: str = "",
    category: str = "",
    search_key: str = "",
    plate: str = "",
    trade: str = "",
    sort_name: str = "",
    sort_type: str = "",
    highlight_title: bool = True,
) -> dict[str, Any]:
    """单页原始查询。``stock`` 为空时做全市场切片（需配合 plate/category/日期）。"""
    form = list_form(
        stock=stock,
        page_num=page_num,
        page_size=page_size,
        column=column,
        tab=tab,
        se_date=se_date,
        category=category,
        search_key=search_key,
        plate=plate,
        trade=trade,
        sort_name=sort_name,
        sort_type=sort_type,
        highlight_title=highlight_title,
    )
    payload = _post_json(QUERY_URL, data=form, headers=FORM_HEADERS)
    if not isinstance(payload, dict):
        return {
            "announcements": [],
            "totalAnnouncement": 0,
            "totalpages": 0,
            "hasMore": False,
        }
    return payload


def fetch_pages(params: dict[str, Any]) -> dict[str, Any]:
    """按 params 翻页，只保存各页原始 JSON。"""
    pages: list[dict[str, Any]] = []
    total = 0
    total_pages = 1
    page = 1
    limit = params["max_pages"]
    while page <= total_pages and page <= limit:
        try:
            payload = query_page(
                stock=params["stock"],
                page_num=page,
                column=params["column"],
                tab=params["tab"],
                se_date=params["se_date"],
                category=params["category"],
                search_key=params["keyword"],
                plate=params["plate"],
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("hisAnnouncement 失败 page=%s: %s", page, exc)
            break
        rows = payload.get("announcements") or []
        total = int(payload.get("totalAnnouncement") or payload.get("totalRecordNum") or 0)
        total_pages = int(payload.get("totalpages") or 1)
        has_more = bool(payload.get("hasMore"))
        if not isinstance(rows, list) or not rows:
            break
        pages.append(payload)
        if page >= total_pages and not has_more:
            break
        page += 1
        if page <= total_pages and page <= limit:
            time.sleep(REQUEST_PAUSE_SEC)
    return {"pages": pages, "total": total}


def download_pdf(url: str, dest: str | Path) -> Path:
    """下载一条公告 PDF。"""
    dest_path = Path(dest)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    data = get_bytes(
        url,
        headers={"Referer": "https://www.cninfo.com.cn/"},
        timeout=60,
    )
    dest_path.write_bytes(data)
    return dest_path


def download_announcements(
    items: Iterable[dict[str, Any]],
    dest_dir: str | Path,
    *,
    limit: int = 0,
) -> list[Path]:
    """批量下载列表里的 PDF。``limit<=0`` 表示全部。"""
    folder = Path(dest_dir)
    folder.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    for i, item in enumerate(items):
        if limit > 0 and i >= limit:
            break
        url = safe_str(item.get("url"))
        if not url:
            continue
        name = safe_filename(
            safe_str(item.get("title")),
            safe_str(item.get("announcement_id")),
            url,
        )
        saved.append(download_pdf(url, folder / name))
        time.sleep(REQUEST_PAUSE_SEC)
    return saved
