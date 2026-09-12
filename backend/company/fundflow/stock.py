"""个股资金流向：历史日线、当日分钟、当日快照。"""

from __future__ import annotations

from typing import Any

from company.fundflow._common import (
    _DAILY_FIELDS2,
    _MINUTE_FIELDS2,
    _SNAPSHOT_FIELDS,
    fetch_fflow_klines,
    parse_daily_line,
    parse_minute_line,
    parse_snapshot_row,
    request_push2,
)
from company.line.eastmoney_kline import resolve_secid
from core.codes import normalize_code


def fetch_daily(code: str, *, limit: int = 120) -> dict[str, Any]:
    """历史日线：小单 / 中单 / 大单 / 超大单净流入及净占比。"""
    sid = resolve_secid(code)
    norm = normalize_code(code)
    if not sid:
        raise ValueError("无效股票代码")
    cap = min(max(int(limit or 120), 1), 120)
    items, meta = fetch_fflow_klines(
        secid=sid,
        klt=101,
        limit=cap,
        fields2=_DAILY_FIELDS2,
        parser=parse_daily_line,
        use_his=True,
        code=norm,
    )
    return {
        "code": meta.get("code") or norm,
        "secid": sid,
        "name": meta.get("name") or "",
        "period": "day",
        "source": "eastmoney" if items else "",
        "count": len(items),
        "items": items,
    }


def fetch_minute(code: str, *, limit: int = 240, klt: int = 1) -> dict[str, Any]:
    """当日分钟资金流。非交易时段可能为空。"""
    sid = resolve_secid(code)
    norm = normalize_code(code)
    if not sid:
        raise ValueError("无效股票代码")
    if klt not in {1, 5, 15, 30, 60}:
        raise ValueError("klt 须为 1 | 5 | 15 | 30 | 60")
    items, meta = fetch_fflow_klines(
        secid=sid,
        klt=klt,
        limit=limit,
        fields2=_MINUTE_FIELDS2,
        parser=parse_minute_line,
        use_his=False,
    )
    return {
        "code": meta.get("code") or norm,
        "secid": sid,
        "name": meta.get("name") or "",
        "period": f"{klt}m",
        "klt": klt,
        "source": "eastmoney" if items else "",
        "count": len(items),
        "items": items,
    }


def fetch_snapshot(code: str) -> dict[str, Any]:
    """当日五档资金流快照。"""
    sid = resolve_secid(code)
    norm = normalize_code(code)
    if not sid:
        raise ValueError("无效股票代码")
    payload = request_push2(
        "/api/qt/ulist.np/get",
        params={
            "fltt": 2,
            "secids": sid,
            "fields": _SNAPSHOT_FIELDS,
            "ut": "b2884a393a59ad64002292a3e90d46a5",
        },
    )
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    diff = data.get("diff") or []
    row = diff[0] if diff else {}
    flow = parse_snapshot_row(row if isinstance(row, dict) else {})
    return {
        "code": norm,
        "secid": sid,
        "name": str(row.get("f14") or "").strip() if isinstance(row, dict) else "",
        "period": "snapshot",
        "source": "eastmoney",
        **flow,
    }
