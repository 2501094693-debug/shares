"""东财国内期货列表（clist/get）。"""

from __future__ import annotations

import logging
import math
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from core.fmt import fmt_pct, fmt_price, fmt_signed, fmt_volume_hands, fmt_yi_wan, to_float
from core.http import get_json

from market.futures import taxonomy

logger = logging.getLogger(__name__)

_UT = "bd1d9ddb04089700cf9c27f6f7426281"
_PAGE = 200
_HEADERS = {
    "Referer": "https://quote.eastmoney.com/center/gridlist.html#futures_qh",
    "Accept": "application/json, text/plain, */*",
}
_FIELDS = (
    "f12,f13,f14,f2,f3,f4,f5,f6,f7,f15,f16,f17,f18,f108,f109"
)
_HOSTS = (
    "https://push2delay.eastmoney.com/api/qt/clist/get",
    "https://push2.eastmoney.com/api/qt/clist/get",
    "https://88.push2.eastmoney.com/api/qt/clist/get",
    "https://71.push2.eastmoney.com/api/qt/clist/get",
)
_FAIL_COOLDOWN_SEC = 45.0
_PAGE_ROUNDS = 3
_WORKERS = 3

# 主力：名称含「主力」，或代码以 m 结尾，或纯字母短码（如 rb / au / IM）
_MAIN_CODE_RE = re.compile(r"^[A-Za-z]{1,4}m?$", re.ASCII)

_good_lock = threading.Lock()
_good_host: str | None = None
_host_fail_until: dict[str, float] = {}


def _mark_good(url: str) -> None:
    global _good_host
    with _good_lock:
        _good_host = url
        _host_fail_until.pop(url, None)


def _mark_fail(url: str) -> None:
    global _good_host
    with _good_lock:
        _host_fail_until[url] = time.monotonic() + _FAIL_COOLDOWN_SEC
        if _good_host == url:
            _good_host = None


def _hosts() -> list[str]:
    now = time.monotonic()
    with _good_lock:
        preferred = _good_host
        dead = {host for host, until in _host_fail_until.items() if until > now}
    hosts = [host for host in _HOSTS if host not in dead] or list(_HOSTS)
    if preferred in hosts:
        hosts.remove(preferred)
        hosts.insert(0, preferred)
    return hosts


def _page(fs: str, pn: int) -> dict[str, Any]:
    params = {
        "pn": str(pn),
        "pz": str(_PAGE),
        "po": "1",
        "np": "1",
        "fltt": "2",
        "invt": "2",
        "wbp2u": "|0|0|0|web",
        "fid": "f3",
        "fs": fs,
        "fields": _FIELDS,
        "ut": _UT,
    }
    last_error: Exception | None = None
    for round_i in range(_PAGE_ROUNDS):
        for url in _hosts():
            try:
                payload = get_json(
                    url,
                    params=params,
                    headers=_HEADERS,
                    timeout=(6, 20),
                    retries=1,
                )
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                _mark_fail(url)
                logger.info("东财期货列表 %s pn=%s 失败: %s", url.split("/")[2], pn, exc)
                continue
            data = payload.get("data") if isinstance(payload, dict) else None
            if isinstance(data, dict):
                _mark_good(url)
                return payload
            last_error = RuntimeError("东财期货列表返回非 JSON")
        time.sleep(0.4 * (round_i + 1))
    raise RuntimeError(f"东财期货列表失败: {last_error}")


def _rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data") or {}
    diff = data.get("diff") or []
    if isinstance(diff, dict):
        diff = list(diff.values())
    return [item for item in diff if isinstance(item, dict)]


def _is_main(code: str, name: str) -> bool:
    if "主力" in name:
        return True
    lowered = code.lower()
    if lowered.endswith("m") and _MAIN_CODE_RE.match(code):
        return True
    # 纯品种短码（无月份）：rb / au / IF / IM
    if code.isalpha() and 1 <= len(code) <= 4:
        return True
    return False


def _normalize_row(item: dict[str, Any], category_code: str) -> dict[str, Any]:
    code = str(item.get("f12") or "").strip()
    market_id = to_float(item.get("f13"))
    mid = int(market_id) if market_id is not None else None
    cat = taxonomy.get_category(category_code) or {}
    venue = cat.get("venue") or ""
    if not venue and mid is not None:
        mapped = taxonomy.MARKET_ID_TO_CATEGORY.get(mid)
        if mapped:
            venue = (taxonomy.get_category(mapped) or {}).get("venue", "")
    name = str(item.get("f14") or "").strip()
    full_code = f"{code}.{venue}" if code and venue else code
    return {
        "code": code,
        "full_code": full_code,
        "name": name,
        "venue": venue,
        "market_id": mid,
        "category_code": category_code,
        "is_main": _is_main(code, name),
        "price": fmt_price(item.get("f2")),
        "change_pct": fmt_pct(item.get("f3")),
        "change": fmt_signed(item.get("f4")),
        "volume": fmt_volume_hands(item.get("f5")),
        "amount": fmt_yi_wan(item.get("f6")),
        "amplitude": fmt_pct(item.get("f7")),
        "high": fmt_price(item.get("f15")),
        "low": fmt_price(item.get("f16")),
        "open": fmt_price(item.get("f17")),
        "prev_close": fmt_price(item.get("f18")),
        "open_interest": fmt_volume_hands(item.get("f108")),
        "oi_change_pct": fmt_pct(item.get("f109")),
    }


def fetch_category_total(fs: str) -> int:
    """只取分类总数，不拉全量列表。"""
    payload = _page(fs, 1)
    data = payload.get("data") or {}
    return int(to_float(data.get("total")) or 0)


def fetch_category_list(fs: str, category_code: str) -> tuple[list[dict[str, Any]], int]:
    """拉取某交易所下全部期货合约。"""
    first = _page(fs, 1)
    data = first.get("data") or {}
    total = int(to_float(data.get("total")) or 0)
    first_rows = _rows(first)
    page_size = len(first_rows) or _PAGE
    pages = max(1, math.ceil(total / page_size)) if total else 1
    batches = [first_rows]

    if pages > 1:
        rest = list(range(2, pages + 1))
        by_pn: dict[int, list[dict[str, Any]]] = {}
        with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
            futs = {pool.submit(_page, fs, pn): pn for pn in rest}
            for fut in as_completed(futs):
                pn = futs[fut]
                try:
                    by_pn[pn] = _rows(fut.result())
                except Exception as exc:  # noqa: BLE001
                    logger.info("东财期货列表 pn=%s 重试: %s", pn, exc)
                    time.sleep(0.6)
                    by_pn[pn] = _rows(_page(fs, pn))
        for pn in rest:
            batches.append(by_pn.get(pn, []))

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for batch in batches:
        for row in batch:
            code = str(row.get("f12") or "").strip()
            if not code or code in seen:
                continue
            seen.add(code)
            items.append(_normalize_row(row, category_code))
    return items, total
