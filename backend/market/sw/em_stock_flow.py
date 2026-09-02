"""东财全市场个股资金流，用来按申万成分股加总到行业。"""

from __future__ import annotations

import logging
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from core.fmt import to_float
from core.http import get_json

logger = logging.getLogger(__name__)

_UT = "b2884a393a59ad64002292a3e90d46a5"
_FS = (
    "m:0+t:6+f:!2,m:0+t:13+f:!2,m:0+t:80+f:!2,"
    "m:1+t:2+f:!2,m:1+t:23+f:!2,m:0+t:7+f:!2,m:1+t:3+f:!2"
)
_FIELDS = (
    "f12,f14,f2,f3,f62,f184,f66,f72,f78,f84,"
    "f115,f23,"
    "f164,f165,f174,f175"
)
_HEADERS = {
    "Referer": "https://data.eastmoney.com/zjlx/detail.html",
    "Accept": "application/json, text/plain, */*",
}
_PAGE = 200
# push2 / 数字节点经常被对端掐线；delay 相对稳。失败节点短冷却，避免并发全打到死节点。
_HOSTS = (
    "https://push2delay.eastmoney.com/api/qt/clist/get",
    "https://push2.eastmoney.com/api/qt/clist/get",
    "https://71.push2.eastmoney.com/api/qt/clist/get",
    "https://82.push2.eastmoney.com/api/qt/clist/get",
    "https://88.push2.eastmoney.com/api/qt/clist/get",
    "https://79.push2.eastmoney.com/api/qt/clist/get",
)
_FAIL_COOLDOWN_SEC = 45.0
_PAGE_ROUNDS = 3
_WORKERS = 3


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


def _page(pn: int) -> dict[str, Any]:
    params = {
        "pn": str(pn),
        "pz": str(_PAGE),
        "po": "1",
        "np": "1",
        "fltt": "2",
        "invt": "2",
        "fid": "f62",
        "fs": _FS,
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
                logger.info("东财资金流 %s pn=%s 失败: %s", url.split("/")[2], pn, exc)
                continue
            data = payload.get("data") if isinstance(payload, dict) else None
            if isinstance(data, dict):
                _mark_good(url)
                return payload
            last_error = RuntimeError("东财个股资金流返回非 JSON")
        time.sleep(0.4 * (round_i + 1))
    raise RuntimeError(f"东财个股资金流失败: {last_error}")


def _rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data") or {}
    diff = data.get("diff") or []
    if isinstance(diff, dict):
        diff = list(diff.values())
    return [item for item in diff if isinstance(item, dict)]


def fetch_stock_flows() -> dict[str, dict[str, Any]]:
    """股票短码 → 今日 / 5 日 / 10 日主力及分档净额。"""
    first = _page(1)
    data = first.get("data") or {}
    total = int(to_float(data.get("total")) or 0)
    first_rows = _rows(first)
    # 东财常把 pz 截成 100，必须按实际页长算页数，否则会漏一半。
    page_size = len(first_rows) or _PAGE
    pages = max(1, math.ceil(total / page_size)) if total else 1
    batches = [first_rows]

    if pages > 1:
        rest = list(range(2, pages + 1))
        by_pn: dict[int, list[dict[str, Any]]] = {}
        with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
            futs = {pool.submit(_page, pn): pn for pn in rest}
            for fut in as_completed(futs):
                pn = futs[fut]
                try:
                    by_pn[pn] = _rows(fut.result())
                except Exception as exc:  # noqa: BLE001
                    logger.info("东财资金流 pn=%s 重试: %s", pn, exc)
                    time.sleep(0.6)
                    by_pn[pn] = _rows(_page(pn))
        for pn in rest:
            batches.append(by_pn[pn])

    out: dict[str, dict[str, Any]] = {}
    for batch in batches:
        for item in batch:
            code = str(item.get("f12") or "").strip()
            if not code:
                continue
            out[code] = {
                "code": code,
                "name": str(item.get("f14") or "").strip(),
                "price": to_float(item.get("f2")),
                "change_pct": to_float(item.get("f3")),
                "main_net": to_float(item.get("f62")),
                "main_net_pct": to_float(item.get("f184")),
                "super_net": to_float(item.get("f66")),
                "big_net": to_float(item.get("f72")),
                "mid_net": to_float(item.get("f78")),
                "small_net": to_float(item.get("f84")),
                "pe_ttm": to_float(item.get("f115")),
                "pb": to_float(item.get("f23")),
                "main_net_5d": to_float(item.get("f164")),
                "main_net_pct_5d": to_float(item.get("f165")),
                "main_net_10d": to_float(item.get("f174")),
                "main_net_pct_10d": to_float(item.get("f175")),
            }
    return out
