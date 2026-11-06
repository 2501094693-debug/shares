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
        "book": {"depth": 0, "last": None, "bids": [], "asks": []},
        "levels": [],
        "queues": {"bid": [], "ask": []},
        "notes": [],
    }


def shares_to_lots(volume: float | None) -> float | None:
    if volume is None:
        return None
    return round(float(volume) / SHARES_PER_LOT, 4)


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
