"""同花顺委托盘口（thsdk）。

当前可稳定拿到的是 ``list_security_order_books`` 五档买卖合计量，以及
``list_security_price_volume_levels`` 当日分价成交。单笔委托队列明细依赖
A 股 Level-2 权限；账号无权限时 ``orders`` 为空，并在 ``notes`` 标明。
"""

from __future__ import annotations

import logging
import math
from typing import Any

from core.codes import normalize_code
from core.fmt import to_float

logger = logging.getLogger(__name__)

SHARES_PER_LOT = 100.0


def _hq_security(code: str) -> str:
    from company.statistics.fundflow.tonghuashun.hq import hq_security

    return hq_security(code)


def _lots(shares: float | None) -> float:
    if shares is None or shares <= 0:
        return 0.0
    return round(shares / SHARES_PER_LOT, 4)


def _finite(value: Any) -> float | None:
    number = to_float(value)
    if number is None or not math.isfinite(number):
        return None
    return number


def fetch_permissions(*, timeout: float | None = None) -> dict[str, Any]:
    """账号行情权限快照（含 ``a_stock_level2``）。"""
    import thsdk
    from company.line.tonghuashun import auth as _ths_auth

    if not _ths_auth.ensure(timeout=3):
        raise RuntimeError("THS_NEED_QRCODE:同花顺需扫码登录，前端打开扫码弹窗后重试")
    raw = thsdk.account_permissions(timeout=timeout)
    if not isinstance(raw, dict):
        return {"loaded": False, "raw_type": type(raw).__name__}
    return dict(raw)


def _parse_side_levels(
    rows: list[Any] | None,
    *,
    side: str,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for index, row in enumerate(rows or []):
        if not isinstance(row, dict):
            continue
        price = _finite(row.get("price"))
        volume = _finite(row.get("volume")) or 0.0
        if price is None:
            continue
        # 源站仅给合计量；若日后 L2 带出明细，优先用原生 orders
        raw_orders = row.get("orders") or row.get("queue") or row.get("details") or []
        orders: list[dict[str, Any]] = []
        if isinstance(raw_orders, list):
            for seq, item in enumerate(raw_orders):
                if not isinstance(item, dict):
                    continue
                o_vol = _finite(item.get("volume") or item.get("qty") or item.get("amount"))
                if o_vol is None or o_vol <= 0:
                    continue
                orders.append(
                    {
                        "seq": seq + 1,
                        "volume": o_vol,
                        "volume_lots": _lots(o_vol),
                        "order_id": str(
                            item.get("order_id")
                            or item.get("id")
                            or item.get("no")
                            or ""
                        ),
                    }
                )
        out.append(
            {
                "level": index + 1,
                "side": side,
                "price": price,
                "volume": volume,
                "volume_lots": _lots(volume),
                "order_count": len(orders),
                "orders": orders,
            }
        )
    return out


def fetch_order_book(
    code: str,
    *,
    depth: str = "5",
    timeout: float | None = None,
) -> dict[str, Any]:
    """拉买卖档位。无 L2 时每档只有合计量，``orders`` 为空。"""
    import thsdk
    from company.line.tonghuashun import auth as _ths_auth

    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")
    if not _ths_auth.ensure(timeout=3):
        raise RuntimeError("THS_NEED_QRCODE:同花顺需扫码登录，前端打开扫码弹窗后重试")

    security = _hq_security(norm)
    frame = thsdk.list_security_order_books(
        securities=[security],
        depth=str(depth or "5"),
        timeout=timeout,
    )
    records = frame.to_dict("records") if hasattr(frame, "to_dict") else list(frame or [])
    row = next((item for item in records if isinstance(item, dict)), None)
    if not row:
        raise RuntimeError(f"{norm} 委托盘口为空")

    bids = _parse_side_levels(row.get("bids"), side="buy")
    asks = _parse_side_levels(row.get("asks"), side="sell")
    return {
        "code": norm,
        "security": security,
        "depth": str(row.get("depth") or depth or "5"),
        "bids": bids,
        "asks": asks,
        "source": "thsdk:order_books",
    }


def fetch_price_volume_levels(
    code: str,
    *,
    timeout: float | None = None,
) -> list[dict[str, Any]]:
    """当日分价成交（每个价位的成交量 / 内外盘），不是排队委托。"""
    import thsdk
    from company.line.tonghuashun import auth as _ths_auth

    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")
    if not _ths_auth.ensure(timeout=3):
        raise RuntimeError("THS_NEED_QRCODE:同花顺需扫码登录，前端打开扫码弹窗后重试")

    security = _hq_security(norm)
    frame = thsdk.list_security_price_volume_levels(security=security, timeout=timeout)
    records = frame.to_dict("records") if hasattr(frame, "to_dict") else list(frame or [])
    items: list[dict[str, Any]] = []
    for row in records:
        if not isinstance(row, dict):
            continue
        price = _finite(row.get("price"))
        volume = _finite(row.get("volume")) or 0.0
        if price is None or volume <= 0:
            continue
        in_volume = _finite(row.get("in_volume")) or 0.0
        out_volume = _finite(row.get("out_volume")) or 0.0
        try:
            count = int(float(row.get("transaction_count") or 0))
        except (TypeError, ValueError):
            count = 0
        out_rate = _finite(row.get("out_volume_rate"))
        items.append(
            {
                "price": price,
                "volume": volume,
                "volume_lots": _lots(volume),
                "in_volume": in_volume,
                "in_volume_lots": _lots(in_volume),
                "out_volume": out_volume,
                "out_volume_lots": _lots(out_volume),
                "transaction_count": count,
                "out_volume_rate": round(out_rate, 4) if out_rate is not None else None,
            }
        )
    items.sort(key=lambda item: item["price"])
    return items
