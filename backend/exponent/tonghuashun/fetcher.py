"""同花顺指数实时行情：用最近两根日 K 推算点位 / 涨跌。

指数没有可用的五档盘口（``depth`` 对指数常返回 no_data），因此以日 K
最新收盘为现价，前一根收盘为昨收。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from core.fmt import to_float

from exponent.tonghuashun.catalog import all_items
from exponent.tonghuashun.codes import resolve


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


def _row_time(raw: Any) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) >= 8:
        return f"{digits[0:4]}-{digits[4:6]}-{digits[6:8]}"
    return text[:10]


def _quote_from_bars(frame: Any) -> dict[str, Any]:
    quote = _empty_quote()
    if frame is None or len(frame) == 0:
        return quote
    try:
        records = frame.reset_index().to_dict("records")
    except Exception:  # noqa: BLE001
        records = list(frame.to_dict("records")) if hasattr(frame, "to_dict") else []
    if not records:
        return quote

    last = records[-1]
    prev = records[-2] if len(records) >= 2 else None
    close = to_float(last.get("close"))
    prev_close = to_float(prev.get("close")) if prev else None
    change = None
    change_pct = None
    if close is not None and prev_close not in (None, 0):
        change = round(close - prev_close, 4)
        change_pct = round((close / prev_close - 1.0) * 100, 4)

    quote.update(
        {
            "price": close,
            "change": change,
            "change_pct": change_pct,
            "open": to_float(last.get("open")),
            "high": to_float(last.get("high")),
            "low": to_float(last.get("low")),
            "prev_close": prev_close,
            "volume": to_float(last.get("volume")),
            "amount": to_float(last.get("turnover") or last.get("amount")),
            "quote_time": _row_time(last.get("time") or last.get("date")),
        }
    )
    return quote


def _fetch_one(meta: dict[str, Any]) -> dict[str, Any]:
    import thsdk

    security = meta["security"]
    frame = thsdk.klines(security, adjust="", interval="day", count=2)
    quote = _quote_from_bars(frame)
    return {
        "code": meta.get("code") or "",
        "name": meta.get("name") or "",
        "security": security,
        "market": meta.get("market") or security[:4],
        "group": meta.get("group"),
        "group_name": meta.get("group_name"),
        "source": "tonghuashun",
        **quote,
    }


def fetch_quotes(
    codes: list[str] | None = None,
    *,
    workers: int = 6,
) -> dict[str, Any]:
    """拉取指数行情。

    - ``codes`` 为空：目录内全部常用指数；
    - 否则按公开码 / security / 名称解析后拉取。
    """
    from company.line.tonghuashun import auth as _ths_auth

    if not _ths_auth.ensure(timeout=3):
        raise RuntimeError("THS_NEED_QRCODE:同花顺需扫码登录，前端打开扫码弹窗后重试")

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
                        "security": str(meta.get("security") or ""),
                        "error": str(exc),
                    }
                )

    order = {str(m.get("code") or ""): i for i, m in enumerate(metas)}
    items.sort(key=lambda r: order.get(str(r.get("code") or ""), 10_000))
    return {
        "source": "tonghuashun",
        "count": len(items),
        "items": items,
        "errors": errors,
    }
