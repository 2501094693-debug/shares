"""委托盘口统一入口。

优先走同花顺 thsdk 五档；附带账号权限与可选分价成交。单笔委托细则
（买一/卖一队列）要等 ``a_stock_level2`` 或手机端抓包补齐后再填 ``orders``。
"""

from __future__ import annotations

import logging
from typing import Any

from core.codes import normalize_code

from company.line.entrust.ths import (
    fetch_order_book,
    fetch_permissions,
    fetch_price_volume_levels,
)

logger = logging.getLogger(__name__)


def fetch_entrust(
    code: str,
    *,
    depth: str = "5",
    with_price_levels: bool = False,
    with_permissions: bool = True,
    timeout: float | None = None,
) -> dict[str, Any]:
    """拉取一只股票的委托盘口。

    返回字段：

    - ``bids`` / ``asks``：各档 ``price/volume/volume_lots/orders``
    - ``level2``：当前会话是否具备 A 股 Level-2
    - ``queue_detail``：是否至少有一档带出了单笔委托
    - ``price_levels``：可选，当日分价成交（非排队队列）
    """
    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")

    permissions: dict[str, Any] = {}
    notes: list[str] = []
    if with_permissions:
        try:
            permissions = fetch_permissions(timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            logger.info("entrust permissions skip %s: %s", norm, exc)
            notes.append(f"权限探测失败：{exc}")

    book = fetch_order_book(norm, depth=depth, timeout=timeout)
    level2 = bool(permissions.get("a_stock_level2"))
    has_orders = any(
        level.get("orders")
        for side in (book.get("bids") or [], book.get("asks") or [])
        for level in side
    )
    if not level2:
        notes.append(
            "当前同花顺会话无 A 股 Level-2（a_stock_level2=false），"
            "仅返回五档合计量；手机端买卖队列细则需 L2 权限或抓包接入"
        )
    elif not has_orders:
        notes.append(
            "账号声明具备 A 股 Level-2，但 order_books 未返回单笔委托；"
            "队列细则接口仍待补齐"
        )

    pack: dict[str, Any] = {
        "code": norm,
        "source": book.get("source") or "thsdk:order_books",
        "depth": book.get("depth") or str(depth),
        "bids": book.get("bids") or [],
        "asks": book.get("asks") or [],
        "level2": level2,
        "queue_detail": has_orders,
        "permissions": permissions if with_permissions else {},
        "notes": notes,
    }

    if with_price_levels:
        try:
            pack["price_levels"] = fetch_price_volume_levels(norm, timeout=timeout)
            pack["price_levels_source"] = "thsdk:price_volume_levels"
        except Exception as exc:  # noqa: BLE001
            logger.info("entrust price_levels skip %s: %s", norm, exc)
            pack["price_levels"] = []
            notes.append(f"分价成交拉取失败：{exc}")

    return pack
