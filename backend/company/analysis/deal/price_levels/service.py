"""当日分价表：同花顺 thsdk 优先，失败时用逐笔聚合格位。

把当天已成交量按成交价汇总：每个价位一行，含总量 / 内外盘 / 笔数。
这是「价位直方图」，不是买卖队列里的挂单明细，也不是逐笔时间线。
"""

from __future__ import annotations

import logging
from typing import Any

from core.codes import normalize_code
from core.fmt import to_float

logger = logging.getLogger(__name__)

SHARES_PER_LOT = 100.0


def _hq_security(code: str) -> str:
    """HQ 证券代码（``USHA600519`` 格式），延迟导入以避开循环引用。"""
    from company.statistics.fundflow.tonghuashun import hq as _hq

    return _hq.hq_security(code)


def _lots(shares: float | None) -> float | None:
    if shares is None:
        return None
    return round(float(shares) / SHARES_PER_LOT, 4)


def _parse_level(row: dict[str, Any]) -> dict[str, Any] | None:
    price = to_float(row.get("price"))
    volume = to_float(row.get("volume"))
    if price is None or volume is None or volume <= 0:
        return None
    in_volume = to_float(row.get("in_volume"))
    out_volume = to_float(row.get("out_volume"))
    rate = to_float(row.get("out_volume_rate"))
    try:
        count = int(float(row.get("transaction_count") or 0))
    except (TypeError, ValueError):
        count = 0
    return {
        "price": round(price, 4),
        "volume": round(volume, 2),
        "volume_lots": _lots(volume),
        "in_volume": None if in_volume is None else round(in_volume, 2),
        "in_volume_lots": _lots(in_volume),
        "out_volume": None if out_volume is None else round(out_volume, 2),
        "out_volume_lots": _lots(out_volume),
        "transaction_count": count,
        "out_volume_rate": None if rate is None else round(rate, 4),
    }


def _summarize(items: list[dict[str, Any]]) -> dict[str, Any]:
    total_volume = 0.0
    total_in = 0.0
    total_out = 0.0
    total_count = 0
    for row in items:
        total_volume += float(row.get("volume") or 0)
        if row.get("in_volume") is not None:
            total_in += float(row["in_volume"])
        if row.get("out_volume") is not None:
            total_out += float(row["out_volume"])
        total_count += int(row.get("transaction_count") or 0)
    return {
        "level_count": len(items),
        "volume": round(total_volume, 2),
        "volume_lots": _lots(total_volume),
        "in_volume": round(total_in, 2),
        "out_volume": round(total_out, 2),
        "transaction_count": total_count,
        "price_min": items[0]["price"] if items else None,
        "price_max": items[-1]["price"] if items else None,
    }


def _tick_side_bucket(row: dict[str, Any]) -> str:
    """买→外盘 / 卖→内盘；集合竞价等归入总量但不分内外。"""
    label = str(row.get("side_label") or "").strip().lower()
    side = row.get("side")
    if label in {"buy", "主买", "active_buy"} or side in (1, 5, "1", "5", "buy"):
        return "out"
    if label in {"sell", "主卖", "active_sell"} or side in (2, "2", "sell"):
        return "in"
    return ""


def _tick_lots(row: dict[str, Any]) -> float:
    lots = to_float(row.get("volume_lots"))
    if lots is not None and lots > 0:
        return float(lots)
    volume = to_float(row.get("volume"))
    if volume is None or volume <= 0:
        return 0.0
    # 东财 / 腾讯 volume 已是手；同花顺逐笔也会先换成手
    return float(volume)


def _tick_count(row: dict[str, Any]) -> int:
    for key in ("count", "transaction_count", "deal_count"):
        value = to_float(row.get(key))
        if value is not None and value > 0:
            return max(1, int(value))
    return 1


def _levels_from_ticks(code: str) -> tuple[str, list[dict[str, Any]]]:
    """用当日逐笔按价位聚合，作为 thsdk 分价表的降级。"""
    from company.line.fetcher import fetch_ticks

    pack = fetch_ticks(code)
    ticks = pack.get("items") if isinstance(pack, dict) else None
    if not isinstance(ticks, list) or not ticks:
        raise RuntimeError(f"{code} 逐笔为空，无法聚合分价表")

    buckets: dict[float, dict[str, float]] = {}
    for row in ticks:
        if not isinstance(row, dict):
            continue
        price = to_float(row.get("price"))
        lots = _tick_lots(row)
        if price is None or lots <= 0:
            continue
        key = round(float(price), 4)
        slot = buckets.setdefault(key, {"volume": 0.0, "in": 0.0, "out": 0.0, "count": 0.0})
        shares = lots * SHARES_PER_LOT
        slot["volume"] += shares
        slot["count"] += float(_tick_count(row))
        bucket = _tick_side_bucket(row)
        if bucket == "out":
            slot["out"] += shares
        elif bucket == "in":
            slot["in"] += shares

    items: list[dict[str, Any]] = []
    for price, slot in buckets.items():
        volume = float(slot["volume"])
        in_vol = float(slot["in"])
        out_vol = float(slot["out"])
        rate = (out_vol / volume) if volume > 0 else None
        items.append(
            {
                "price": price,
                "volume": round(volume, 2),
                "volume_lots": _lots(volume),
                "in_volume": round(in_vol, 2),
                "in_volume_lots": _lots(in_vol),
                "out_volume": round(out_vol, 2),
                "out_volume_lots": _lots(out_vol),
                "transaction_count": int(slot["count"]),
                "out_volume_rate": None if rate is None else round(rate, 4),
            }
        )
    items.sort(key=lambda row: row["price"])
    if not items:
        raise RuntimeError(f"{code} 逐笔聚合后分价表为空")
    tick_source = str((pack or {}).get("source") or "ticks")
    return f"ticks:{tick_source}", items


def _fetch_ths_price_levels(
    code: str,
    *,
    timeout: float | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    import thsdk
    from company.line.tonghuashun import auth as _ths_auth

    if not _ths_auth.ensure(timeout=3):
        raise RuntimeError("THS_NEED_QRCODE:同花顺需扫码登录，前端打开扫码弹窗后重试")

    security = _hq_security(code)
    if not security:
        raise ValueError("无法映射同花顺证券代码")

    kwargs: dict[str, Any] = {"security": security}
    if timeout is not None:
        kwargs["timeout"] = timeout
    frame = thsdk.list_security_price_volume_levels(**kwargs)
    records = frame.to_dict("records") if hasattr(frame, "to_dict") else list(frame or [])
    items: list[dict[str, Any]] = []
    for row in records:
        if not isinstance(row, dict):
            continue
        parsed = _parse_level(row)
        if parsed:
            items.append(parsed)
    items.sort(key=lambda row: row["price"])
    if not items:
        raise RuntimeError(f"{code} 分价表为空（非交易日或无权限）")
    return "thsdk:price_volume_levels", items


def fetch_price_levels(
    code: str,
    *,
    timeout: float | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """拉取当日分价表。

    返回 ``(method, items)``，``items`` 按 ``price`` 升序。
    每条为 ``{price/volume/volume_lots/in_volume/out_volume/
    transaction_count/out_volume_rate}``，``volume`` 单位为股。

    同花顺通道失败时自动降级为逐笔聚合。
    """
    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")

    try:
        return _fetch_ths_price_levels(norm, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        # 未登录 / 通道异常都走逐笔降级（东财/腾讯不依赖同花顺会话）
        logger.info("price_levels thsdk skip %s: %s", norm, exc)

    method, items = _levels_from_ticks(norm)
    return method, items


def fetch_price_levels_pack(
    code: str,
    *,
    timeout: float | None = None,
    around: float | None = None,
    span: float | None = None,
    limit: int = 0,
) -> dict[str, Any]:
    """统一分价表包，便于 CLI / 上层直接取用。"""
    norm = normalize_code(code)
    method, items = fetch_price_levels(norm, timeout=timeout)
    summary = _summarize(items)
    source = "ticks" if str(method).startswith("ticks:") else "tonghuashun"

    view = items
    if around is not None:
        center = float(around)
        half = float(span) if span is not None and span > 0 else 5.0
        lo, hi = center - half, center + half
        view = [row for row in items if lo <= float(row["price"]) <= hi]
    if limit and limit > 0 and len(view) > limit:
        # 无 around 时取成交量最大的 N 档，便于预览
        if around is None:
            view = sorted(view, key=lambda row: float(row["volume"]), reverse=True)[:limit]
            view.sort(key=lambda row: row["price"])
        else:
            view = view[:limit]

    notes = ["分价表为当日各价位已成交汇总，不是买卖队列挂单明细"]
    if source == "ticks":
        notes.append("同花顺分价通道不可用，已用当日逐笔按价位聚合（内外盘按主买/主卖）")

    return {
        "code": norm,
        "period": "price_levels",
        "source": source,
        "method": method,
        "count": len(view),
        "total_count": len(items),
        "summary": summary,
        "items": view,
        "notes": notes,
    }
