"""同花顺实时逐笔到秒（``thsdk.list_security_ticks``，需实盘扫码登录）。

仅交易日当盘有数，周末 / 盘后报 ``no_data`` 属正常。
"""

from __future__ import annotations

from typing import Any

from company.line.session import parse_session_day, session_day
from core.codes import normalize_code
from core.fmt import to_float


def _hq_security(code: str) -> str:
    """HQ 证券代码（``USHA600519`` 格式），延迟导入以避开循环引用。"""
    from company.statistics.fundflow.tonghuashun import hq as _hq

    return _hq.hq_security(code)


def fetch_time_and_sales(
    code: str,
    *,
    day: str = "",
    start: str = "",
    end: str = "",
    count: int = 0,
) -> tuple[str, list[dict[str, Any]]]:
    """逐笔到秒（``list_security_ticks``，需实盘扫码登录）。

    - ``count>0``：最近 ``count`` 笔（单次上限约 300 笔）。
    - 默认拉一整交易日：按 5 分钟切片分页（单次上限约 100 笔，满页自动减半），
      以 ``(time, transaction_count)`` 去重。``day`` 为空即当前交易日。
    - ``start/end`` 可指定 ``HH:MM``（如 ``start="09:30", end="09:35"``）只拉片段。
    - 每条为 ``{time/code/price/volume/amount/side/side_label/deal_type/
      transaction_count}``，``volume`` 单位为股。
    """
    import thsdk

    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")
    if not thsdk.auth_qrcode(timeout=10):
        raise RuntimeError("thsdk 会话复用失败，请重新扫码登录")
    security = _hq_security(norm)

    def _one(window: dict[str, Any]) -> list[dict[str, Any]]:
        frame = thsdk.list_security_ticks(security=security, window=window)
        records = frame.to_dict("records") if hasattr(frame, "to_dict") else list(frame)
        return [dict(r) for r in records if isinstance(r, dict)]

    if count and not (start or end):
        records = _one({"count": max(int(count), 1)})
        return "thsdk:ticks", [parsed for r in records
                               if (parsed := _parse_tick(norm, r))]

    want = (parse_session_day(day) or session_day()).isoformat()
    s_min = _hhmm(start) or (9 * 60 + 30)
    e_min = _hhmm(end) or (15 * 60 + 30)
    slices = [(s_min + i * 5, min(s_min + (i + 1) * 5, e_min))
              for i in range((e_min - s_min + 4) // 5)]

    seen: set[tuple[Any, Any]] = set()
    items: list[dict[str, Any]] = []
    stack = list(slices)
    while stack:
        lo, hi = stack.pop(0)
        window = {
            "start": f"{want}T{lo // 60:02d}:{lo % 60:02d}:00+08:00",
            "end": f"{want}T{hi // 60:02d}:{hi % 60:02d}:00+08:00",
        }
        try:
            records = _one(window)
        except Exception as exc:  # noqa: BLE001
            if "no_data" in str(exc):
                continue
            raise
        if len(records) >= 100 and hi - lo > 1:
            mid = (lo + hi) // 2
            stack.insert(0, (lo, mid))
            stack.insert(1, (mid, hi))
            continue
        for r in records:
            key = (r.get("time"), r.get("transaction_count"))
            if key in seen:
                continue
            seen.add(key)
            parsed = _parse_tick(norm, r)
            if parsed:
                items.append(parsed)
    items.sort(key=lambda r: (str(r.get("time") or ""), _tick_seq(r)))
    if not items:
        raise RuntimeError(f"逐笔返回空（{want} 非交易日或无权限）")
    return "thsdk:ticks", items


_TICK_SIDE = {5: ("buy", "主买"), 1: ("sell", "主卖"), 0: ("neutral", "中性")}


def _tick_seq(row: dict[str, Any]) -> int:
    try:
        return int(row.get("seq") or 0)
    except (TypeError, ValueError):
        return 0


def _parse_tick(code: str, row: dict[str, Any]) -> dict[str, Any] | None:
    from datetime import datetime, timezone, timedelta

    price = to_float(row.get("price"))
    volume = to_float(row.get("volume"))
    if price is None or not volume:
        return None
    try:
        ts = int(float(row.get("time")))
    except (TypeError, ValueError):
        return None
    stamp = datetime.fromtimestamp(
        ts, timezone(timedelta(hours=8))).strftime("%Y%m%d %H:%M:%S")
    try:
        deal = int(float(row.get("deal_type")))
    except (TypeError, ValueError):
        deal = -1
    side, label = _TICK_SIDE.get(deal, ("", ""))
    return {
        "time": stamp,
        "stamp": stamp[9:],
        "code": code,
        "price": price,
        "volume": volume,
        "volume_lots": round(volume / 100.0, 2),
        "amount": round(price * volume, 2),
        "side": side,
        "side_label": label,
        "deal_type": deal,
        "seq": _tick_seq({"seq": row.get("transaction_count")}),
        "event_id": f"{ts}|{row.get('transaction_count')}",
    }


def _hhmm(value: str) -> int | None:
    text = (value or "").strip()
    if not text:
        return None
    parts = text.replace("：", ":").split(":")
    try:
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
    except (TypeError, ValueError):
        return None
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return hour * 60 + minute
    return None
