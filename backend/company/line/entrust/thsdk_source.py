"""同花顺 thsdk：五档盘口 + 分价表 + 账号 Level-2 权限。

- ``list_security_order_books``：买卖各 N 档价量（当前枚举仅 ``depth=5``）
- ``list_security_price_volume_levels``：当日各价位已成交量（分价表）
- ``account_permissions``：是否开通 ``a_stock_level2``

买一/卖一前 50 笔委托细则依赖 A 股 Level-2；无权限时本源不会伪造明细。
"""

from __future__ import annotations

import logging
from typing import Any

from core.codes import normalize_code
from core.fmt import to_float

from company.line.entrust.models import (
    empty_pack,
    normalize_level,
    normalize_order,
    normalize_price_level,
)

logger = logging.getLogger(__name__)


def _hq_security(code: str) -> str:
    from company.statistics.fundflow.tonghuashun import hq as _hq

    return _hq.hq_security(code)


def _ensure_auth(*, timeout: float = 3.0) -> None:
    from company.line.tonghuashun import auth as _ths_auth

    if not _ths_auth.ensure(timeout=timeout):
        raise RuntimeError("THS_NEED_QRCODE:同花顺需扫码登录，前端打开扫码弹窗后重试")


def fetch_permissions(*, timeout: float = 8.0) -> dict[str, Any]:
    """账号权限快照；失败返回空 dict。"""
    import thsdk

    _ensure_auth()
    try:
        raw = thsdk.account_permissions(timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        logger.info("entrust permissions skip: %s", exc)
        return {}
    return dict(raw) if isinstance(raw, dict) else {}


def _parse_book_side(
    rows: Any,
    *,
    with_orders: bool,
) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    for index, item in enumerate(rows):
        if not isinstance(item, dict):
            continue
        orders: list[dict[str, Any]] = []
        raw_orders = item.get("orders") or item.get("queue") or item.get("details")
        if with_orders and isinstance(raw_orders, list):
            for seq, detail in enumerate(raw_orders, start=1):
                if isinstance(detail, dict):
                    parsed = normalize_order(
                        seq=seq,
                        volume=detail.get("volume") or detail.get("vol"),
                        order_id=detail.get("order_id") or detail.get("id"),
                    )
                else:
                    parsed = normalize_order(seq=seq, volume=detail)
                if parsed:
                    orders.append(parsed)
        level = normalize_level(
            level=index + 1,
            price=item.get("price"),
            volume=item.get("volume"),
            orders=orders,
        )
        if level:
            out.append(level)
    return out


def fetch_order_book(
    code: str,
    *,
    depth: str = "5",
    timeout: float = 8.0,
) -> dict[str, Any]:
    """五档（或源站支持的深度）买卖盘。"""
    import thsdk

    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")
    security = _hq_security(norm)
    if not security:
        raise ValueError("无法映射同花顺证券代码")

    _ensure_auth()
    perms = fetch_permissions(timeout=timeout)
    has_l2 = bool(perms.get("a_stock_level2") or perms.get("a_stock_extended_level2"))

    frame = thsdk.list_security_order_books(
        securities=[security],
        depth=str(depth or "5"),
        timeout=timeout,
    )
    pack = empty_pack(norm)
    pack["source"] = "thsdk:order_books"
    pack["permissions"] = perms

    rows = frame.to_dict("records") if hasattr(frame, "to_dict") else []
    row = next((item for item in rows if isinstance(item, dict)), None)
    if not row:
        pack["notes"].append("order_books 返回空")
        return pack

    bids = _parse_book_side(row.get("bids"), with_orders=has_l2)
    asks = _parse_book_side(row.get("asks"), with_orders=has_l2)
    depth_n = max(len(bids), len(asks), int(to_float(row.get("depth")) or 0))
    pack["book"] = {
        "depth": depth_n,
        "last": None,
        "pre_close": None,
        "bids": bids,
        "asks": asks,
    }
    if not has_l2:
        pack["notes"].append(
            "当前同花顺会话无 A 股 Level-2（a_stock_level2=false），"
            "仅有各档委托总量，无买一/卖一委托单细则"
        )
    else:
        # 有 L2 时，把带明细的档位同步到 queues（通常是买一/卖一）
        pack["queues"] = {
            "bid": [b for b in bids if b.get("orders")],
            "ask": [a for a in asks if a.get("orders")],
        }
        if not pack["queues"]["bid"] and not pack["queues"]["ask"]:
            pack["notes"].append(
                "账号具备 Level-2，但 order_books 未返回 orders 明细；"
                "委托队列可能走独立通道，需继续抓包补齐"
            )
    return pack


def fetch_price_levels(
    code: str,
    *,
    timeout: float = 8.0,
) -> dict[str, Any]:
    """当日分价表（各价位已成交量），不是实时排队委托。"""
    import thsdk

    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")
    security = _hq_security(norm)
    if not security:
        raise ValueError("无法映射同花顺证券代码")

    _ensure_auth()
    frame = thsdk.list_security_price_volume_levels(security=security, timeout=timeout)
    pack = empty_pack(norm)
    pack["source"] = "thsdk:price_volume_levels"
    rows = frame.to_dict("records") if hasattr(frame, "to_dict") else []
    levels: list[dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        parsed = normalize_price_level(item)
        if parsed:
            levels.append(parsed)
    levels.sort(key=lambda row: row["price"])
    pack["levels"] = levels
    pack["notes"].append("levels 为当日分价成交，不是买卖队列中的挂单明细")
    return pack
