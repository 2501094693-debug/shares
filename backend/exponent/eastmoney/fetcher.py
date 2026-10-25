"""东财指数实时行情：``push2`` ``/api/qt/stock/get``。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

from core.fmt import to_float
from core.http import get_json

from exponent.eastmoney.catalog import all_items
from exponent.eastmoney.codes import resolve

_HOSTS = (
    "https://push2.eastmoney.com",
    "https://push2delay.eastmoney.com",
    "https://82.push2.eastmoney.com",
)
_FIELDS = "f57,f58,f43,f169,f170,f46,f44,f45,f60,f86,f47,f48"
_HEADERS = {
    "Referer": "https://quote.eastmoney.com/",
    "Accept": "application/json, text/plain, */*",
}
_UT = "fa5fd1943c7b386f172d6893dbfba10b"


def _empty_quote() -> dict[str, Any]:
    return {
        "price": None,
        "change": None,
        "change_pct": None,
        "open": None,
        "high": None,
        "low": None,
        "prev_close": None,
        "volume": None,
        "amount": None,
        "quote_time": None,
    }


def _fmt_quote_time(raw: Any) -> str | None:
    if raw is None or raw == "" or raw == "-":
        return None
    if isinstance(raw, float) and raw.is_integer():
        raw = int(raw)
    text = str(raw).strip()
    if not text:
        return None
    if text.isdigit() and len(text) == 14:
        return (
            f"{text[:4]}-{text[4:6]}-{text[6:8]} "
            f"{text[8:10]}:{text[10:12]}:{text[12:14]}"
        )
    if text.isdigit() and len(text) in (10, 13):
        try:
            n = int(text)
        except ValueError:
            return text
        if n <= 0:
            return None
        ts = n / 1000.0 if len(text) == 13 else float(n)
        try:
            dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone()
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except (OSError, OverflowError, ValueError):
            return text
    return text


def _from_em(data: dict[str, Any]) -> dict[str, Any]:
    quote = _empty_quote()
    quote.update(
        {
            "price": to_float(data.get("f43")),
            "change": to_float(data.get("f169")),
            "change_pct": to_float(data.get("f170")),
            "open": to_float(data.get("f46")),
            "high": to_float(data.get("f44")),
            "low": to_float(data.get("f45")),
            "prev_close": to_float(data.get("f60")),
            "volume": to_float(data.get("f47")),
            "amount": to_float(data.get("f48")),
            "quote_time": _fmt_quote_time(data.get("f86")),
        }
    )
    return quote


def _fetch_one(meta: dict[str, Any]) -> dict[str, Any]:
    secid = meta["secid"]
    params = {
        "fltt": "2",
        "invt": "2",
        "secid": secid,
        "fields": _FIELDS,
        "ut": _UT,
    }
    quote = _empty_quote()
    name = meta.get("name") or ""
    code = meta.get("code") or ""
    for host in _HOSTS:
        try:
            payload = get_json(
                f"{host}/api/qt/stock/get",
                params=params,
                headers=_HEADERS,
                timeout=6,
            )
        except Exception:  # noqa: BLE001
            continue
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict) or data.get("f43") in (None, "-", ""):
            continue
        quote = _from_em(data)
        name = str(data.get("f58") or name).strip()
        code = str(data.get("f57") or code).strip()
        break

    return {
        "code": code,
        "name": name,
        "secid": secid,
        "group": meta.get("group"),
        "group_name": meta.get("group_name"),
        "source": "eastmoney",
        **quote,
    }


def fetch_quotes(
    codes: list[str] | None = None,
    *,
    workers: int = 6,
) -> dict[str, Any]:
    """拉取指数行情。``codes`` 为空则拉目录全部。"""
    if codes:
        metas = [resolve(c) for c in codes if str(c).strip()]
    else:
        metas = all_items()

    items: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    workers = max(1, min(int(workers or 6), 12))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_fetch_one, meta): meta for meta in metas}
        for fut in as_completed(futures):
            meta = futures[fut]
            try:
                items.append(fut.result())
            except Exception as exc:  # noqa: BLE001
                errors.append(
                    {
                        "code": str(meta.get("code") or ""),
                        "secid": str(meta.get("secid") or ""),
                        "error": str(exc),
                    }
                )

    order = {str(m.get("code") or ""): i for i, m in enumerate(metas)}
    items.sort(key=lambda r: order.get(str(r.get("code") or ""), 10_000))
    return {
        "source": "eastmoney",
        "count": len(items),
        "items": items,
        "errors": errors,
    }
