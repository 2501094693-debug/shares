"""股吧人气榜：``emappdata.eastmoney.com/stockrank``。

    POST /stockrank/getAllCurrentList   全市场当前排名
    POST /stockrank/getHisList          个股历史日排名
    POST /stockrank/getCurrentList      个股当日 10 分钟排名
"""

from __future__ import annotations

import logging
from typing import Any

from core.codes import em_code, normalize_code, safe_str, secid
from core.fmt import to_float
from core.http import get_json

from company.emotion.eastmoney._common import (
    CHANNEL_RANK,
    RANK_API,
    SOURCE,
    empty_pack,
    fmt_dt,
    headers_for,
    list_page_url,
    post_payload,
    rank_page_url,
    resolve_keyword,
    to_int,
)

logger = logging.getLogger(__name__)

APP_ID = "appId01"
GLOBAL_ID = "786e4c21-70dc-435a-93bb-38"
ULIST_API = "https://push2delay.eastmoney.com/api/qt/ulist.np/get"
ULIST_API_FALLBACK = "https://push2.eastmoney.com/api/qt/ulist.np/get"
PAGE_SIZE = 50


def _rank_body(**extra: Any) -> dict[str, Any]:
    body = {"appId": APP_ID, "globalId": GLOBAL_ID, "marketType": ""}
    body.update(extra)
    return body


def _rank_headers() -> dict[str, str]:
    hdrs = headers_for(rank_page_url(), origin="https://guba.eastmoney.com")
    hdrs["Content-Type"] = "application/json; charset=UTF-8"
    return hdrs


def query_hot_page(*, page: int = 1, page_size: int = PAGE_SIZE) -> dict[str, Any]:
    """全市场人气榜单页原始 JSON。"""
    payload = post_payload(
        f"{RANK_API}/getAllCurrentList",
        json_body=_rank_body(pageNo=max(1, int(page)), pageSize=max(1, min(int(page_size), 100))),
        headers=_rank_headers(),
        timeout=20,
    )
    return payload if isinstance(payload, dict) else {}


def query_rank_history(code: str) -> dict[str, Any]:
    """个股历史日排名原始 JSON。"""
    payload = post_payload(
        f"{RANK_API}/getHisList",
        json_body=_rank_body(srcSecurityCode=em_code(code)),
        headers=_rank_headers(),
        timeout=20,
    )
    return payload if isinstance(payload, dict) else {}


def query_rank_intraday(code: str) -> dict[str, Any]:
    """个股当日 10 分钟排名原始 JSON。"""
    payload = post_payload(
        f"{RANK_API}/getCurrentList",
        json_body=_rank_body(srcSecurityCode=em_code(code)),
        headers=_rank_headers(),
        timeout=20,
    )
    return payload if isinstance(payload, dict) else {}


def _sc_code(sc: str) -> str:
    raw = safe_str(sc).upper()
    for prefix in ("SH", "SZ", "BJ"):
        if raw.startswith(prefix):
            return normalize_code(raw[2:])
    return normalize_code(raw)


def _secid_from_sc(sc: str) -> str:
    raw = safe_str(sc).upper()
    if raw.startswith("SH"):
        return f"1.{raw[2:]}"
    if raw.startswith(("SZ", "BJ")):
        return f"0.{raw[2:]}"
    return secid(raw)


def _quote_map(secids: list[str]) -> dict[str, dict[str, Any]]:
    if not secids:
        return {}
    out: dict[str, dict[str, Any]] = {}
    chunk = 50
    for i in range(0, len(secids), chunk):
        part = [s for s in secids[i : i + chunk] if s]
        if not part:
            continue
        payload = None
        last_exc: Exception | None = None
        for url in (ULIST_API, ULIST_API_FALLBACK):
            try:
                payload = get_json(
                    url,
                    params={
                        "fltt": "2",
                        "np": "3",
                        "fields": "f12,f14,f2,f3",
                        "secids": ",".join(part),
                    },
                    headers={"Referer": "https://quote.eastmoney.com/"},
                    timeout=12,
                )
                break
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
        if payload is None:
            logger.info("人气榜行情补全失败: %s", last_exc)
            continue
        diff = ((payload.get("data") or {}).get("diff") or []) if isinstance(payload, dict) else []
        if isinstance(diff, dict):
            diff = list(diff.values())
        for row in diff:
            if not isinstance(row, dict):
                continue
            code = normalize_code(row.get("f12"))
            if code:
                out[code] = row
    return out


def fetch_hot_list(*, page: int = 1, page_size: int = PAGE_SIZE) -> dict[str, Any]:
    """全市场当前人气榜。"""
    try:
        payload = query_hot_page(page=page, page_size=page_size)
    except Exception as exc:  # noqa: BLE001
        logger.warning("人气榜失败: %s", exc)
        return empty_pack(channel=CHANNEL_RANK, error=str(exc), page=rank_page_url())
    rows = payload.get("data") or []
    if not isinstance(rows, list):
        rows = []
    quotes = _quote_map([_secid_from_sc(r.get("sc")) for r in rows if isinstance(r, dict)])
    items: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        sc = safe_str(row.get("sc"))
        code = _sc_code(sc)
        quote = quotes.get(code) or {}
        name = safe_str(quote.get("f14"))
        rank_n = to_int(row.get("rk"))
        price = to_float(quote.get("f2"))
        change = to_float(quote.get("f3"))
        title = f"{rank_n}  {name or sc} {code}".strip()
        items.append(
            {
                "code": code,
                "name": name,
                "sc": sc,
                "rank": rank_n,
                "rank_change": to_int(row.get("rc")),
                "his_rank_change": to_int(row.get("hisRc")),
                "price": price,
                "change_pct": change,
                "title": title,
                "summary": title,
                "published_at": "",
                "url": list_page_url(code),
                "source": SOURCE,
                "channel": CHANNEL_RANK,
                "media_name": f"排名{rank_n}",
            }
        )
    return {
        "code": "",
        "name": "",
        "source": SOURCE,
        "channel": CHANNEL_RANK,
        "kind": "hot_list",
        "count": len(items),
        "total": len(items),
        "items": items,
        "page": rank_page_url(),
        "page_no": page,
    }


def fetch_rank(code_or_name: str) -> dict[str, Any]:
    """个股当前人气 + 当日分钟走势 + 历史日排名。"""
    resolved = resolve_keyword(code_or_name)
    code = resolved["code"] or normalize_code(code_or_name)
    name = resolved["name"]
    page = rank_page_url()
    if not code:
        return empty_pack(channel=CHANNEL_RANK, error="缺少股票代码", page=page)
    try:
        his = query_rank_history(code)
        intra = query_rank_intraday(code)
    except Exception as exc:  # noqa: BLE001
        logger.warning("个股人气失败 %s: %s", code, exc)
        return empty_pack(
            code=code,
            name=name,
            channel=CHANNEL_RANK,
            error=str(exc),
            page=page,
        )
    his_rows = his.get("data") if isinstance(his.get("data"), list) else []
    intra_rows = intra.get("data") if isinstance(intra.get("data"), list) else []
    current = intra_rows[-1] if intra_rows else (his_rows[-1] if his_rows else {})
    rank_n = to_int((current or {}).get("rank"))
    items: list[dict[str, Any]] = []
    for row in his_rows[-30:]:
        if not isinstance(row, dict):
            continue
        day = fmt_dt(row.get("calcTime"))
        rnk = to_int(row.get("rank"))
        items.append(
            {
                "code": code,
                "name": name,
                "rank": rnk,
                "title": f"{day[:10]}  排名 {rnk}",
                "published_at": day,
                "url": list_page_url(code),
                "source": SOURCE,
                "channel": CHANNEL_RANK,
                "kind": "history",
                "media_name": f"排名{rnk}",
            }
        )
    return {
        "code": code,
        "name": name,
        "rank": rank_n,
        "sc": em_code(code),
        "source": SOURCE,
        "channel": CHANNEL_RANK,
        "kind": "stock",
        "current": current or {},
        "intraday": intra_rows,
        "history": his_rows,
        "count": len(items),
        "total": len(his_rows),
        "items": items,
        "page": page,
        "url": list_page_url(code),
        "title": f"{name or code} 人气排名 {rank_n}" if rank_n else f"{name or code} 人气",
    }
