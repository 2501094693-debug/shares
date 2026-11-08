"""委托盘口统一结构。

对外包结构::

    {
      "code": "600519",
      "name": "",
      "source": "thsdk:order_books",
      "permissions": {"a_stock_level2": false, ...},
      "book": {
        "depth": 5,
        "last": 1452.0,
        "bids": [{"level": 1, "price": ..., "volume": ..., "volume_lots": ..., "orders": []}],
        "asks": [...],
      },
      "levels": [  # 分价表（当日各价位已成交），不是排队中的委托
        {"price": ..., "volume": ..., "in_volume": ..., "out_volume": ...,
         "transaction_count": ..., "out_volume_rate": ...},
      ],
      "queues": {  # Level-2 买一/卖一委托单细则；无 L2 权限时为空
        "bid": [{"price": ..., "orders": [{"seq": 1, "volume": ..., "volume_lots": ...}]}],
        "ask": [...],
      },
      "notes": [...],
    }

``orders`` / ``queues`` 只有账号具备 A 股 Level-2（``a_stock_level2``）且源站
返回明细时才会填充；当前扫码会话若无 L2，只保证 ``book`` 五档总量。
"""

from __future__ import annotations

from typing import Any

from core.fmt import to_float

SHARES_PER_LOT = 100.0


def empty_pack(code: str) -> dict[str, Any]:
    return {
        "code": code,
        "name": "",
        "source": "",
        "permissions": {},
        "book": {
            "depth": 0,
            "last": None,
            "pre_close": None,
            "bids": [],
            "asks": [],
        },
        "levels": [],
        "queues": {"bid": [], "ask": []},
        "notes": [],
    }


def infer_last_from_book(
    bids: list[dict[str, Any]] | None,
    asks: list[dict[str, Any]] | None,
) -> float | None:
    """单边盘口时用一档价当现价（涨停只剩买、跌停只剩卖）。"""
    bid1 = to_float((bids or [{}])[0].get("price")) if bids else None
    ask1 = to_float((asks or [{}])[0].get("price")) if asks else None
    if bid1 is not None and ask1 is None:
        return bid1
    if ask1 is not None and bid1 is None:
        return ask1
    return None


def fill_book_last_price(code: str, book: dict[str, Any] | None) -> dict[str, Any] | None:
    """补齐 ``last`` / ``pre_close``。

    HQ ``depth`` 字段 6 是昨收不是现价；thsdk 五档也不带最新价。优先腾讯行情，
    再退回单边盘口推断。
    """
    if not isinstance(book, dict):
        return book
    last = to_float(book.get("last"))
    pre_close = to_float(book.get("pre_close"))
    need_last = last is None or last <= 0
    need_pre = pre_close is None or pre_close <= 0
    if need_last or need_pre:
        try:
            from company.statistics.quote.live.sources import fetch_tencent_quote

            quote = fetch_tencent_quote(code) or {}
            if need_last:
                last = to_float(quote.get("_price_raw")) or to_float(quote.get("price"))
            if need_pre:
                pre_close = to_float(quote.get("prev_close"))
        except Exception:  # noqa: BLE001
            pass
    if need_last and (last is None or last <= 0):
        last = infer_last_from_book(book.get("bids") or [], book.get("asks") or [])
    if last is not None and last > 0:
        book["last"] = round(float(last), 4)
    if pre_close is not None and pre_close > 0:
        book["pre_close"] = round(float(pre_close), 4)
    return book


def shares_to_lots(volume: float | None) -> float | None:
    if volume is None:
        return None
    return round(float(volume) / SHARES_PER_LOT, 4)


# 无买/卖档时源站常见占位：2^31、2^31-1；真实 A 股/可转债价远低于此
_INVALID_PRICE_MIN = 0.0
_INVALID_PRICE_MAX = 1_000_000.0


def normalize_level(
    *,
    level: int,
    price: Any,
    volume: Any,
    orders: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    px = to_float(price)
    vol = to_float(volume)
    if px is None or vol is None:
        return None
    # 空档：量<=0，或价格为占位/离谱值（如 2147483648）
    if vol <= 0 or px <= _INVALID_PRICE_MIN or px >= _INVALID_PRICE_MAX:
        return None
    row: dict[str, Any] = {
        "level": int(level),
        "price": round(px, 4),
        "volume": round(vol, 2),
        "volume_lots": shares_to_lots(vol),
        "orders": orders or [],
    }
    return row


def normalize_order(*, seq: int, volume: Any, order_id: Any = None) -> dict[str, Any] | None:
    vol = to_float(volume)
    if vol is None or vol <= 0:
        return None
    row: dict[str, Any] = {
        "seq": int(seq),
        "volume": round(vol, 2),
        "volume_lots": shares_to_lots(vol),
    }
    if order_id not in (None, ""):
        row["order_id"] = order_id
    return row


def normalize_price_level(row: dict[str, Any]) -> dict[str, Any] | None:
    px = to_float(row.get("price"))
    vol = to_float(row.get("volume"))
    if px is None or vol is None:
        return None
    in_vol = to_float(row.get("in_volume"))
    out_vol = to_float(row.get("out_volume"))
    count = row.get("transaction_count")
    try:
        count_i = int(float(count)) if count is not None else None
    except (TypeError, ValueError):
        count_i = None
    rate = to_float(row.get("out_volume_rate"))
    return {
        "price": round(px, 4),
        "volume": round(vol, 2),
        "volume_lots": shares_to_lots(vol),
        "in_volume": None if in_vol is None else round(in_vol, 2),
        "out_volume": None if out_vol is None else round(out_vol, 2),
        "transaction_count": count_i,
        "out_volume_rate": None if rate is None else round(rate, 4),
    }
