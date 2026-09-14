"""同花顺个股资金流向：当日快照与分钟序列。"""

from __future__ import annotations

from typing import Any

from core.codes import normalize_code

from company.statistics.fundflow.tonghuashun._common import (
    _today_prefix,
    fetch_sp_json,
    parse_diff,
    parse_flash_rows,
    parse_line_points,
    parse_title,
)


def fetch_snapshot(code: str) -> dict[str, Any]:
    """当日实时资金流向快照（DDE 分档流入/流出 + 主力净额）。"""
    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")
    payload = fetch_sp_json(norm, "Funds/realFunds")
    title = parse_title(payload.get("title"))
    flash = parse_flash_rows(payload.get("flash") or [])
    merged = {**flash, **{k: v for k, v in title.items() if v is not None}}
    return {
        "code": norm,
        "name": "",
        "period": "snapshot",
        "source": "tonghuashun" if merged else "",
        **merged,
        "raw": {
            "title": payload.get("title"),
            "flash": payload.get("flash"),
            "field": payload.get("field"),
        },
    }


def fetch_intraday(code: str) -> dict[str, Any]:
    """当日分钟资金流向 + 汇总 diff/dde。"""
    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")
    payload = fetch_sp_json(norm, "Funds/lineFunds")
    items = parse_line_points(str(payload.get("line") or ""))
    summary = parse_diff(payload.get("diff"))
    dde = payload.get("dde") if isinstance(payload.get("dde"), dict) else {}
    if summary.get("main_net") is None:
        summary["main_net"] = parse_title({"je": dde.get("zllx")}).get("main_net")
    return {
        "code": norm,
        "name": "",
        "period": "1m",
        "source": "tonghuashun" if items or any(v is not None for v in summary.values()) else "",
        "count": len(items),
        "items": items,
        "summary": summary,
        "dde": dde,
    }


def fetch_daily(code: str, *, limit: int = 120) -> dict[str, Any]:
    """同花顺 stockpage 未提供稳定的历史日频接口，返回当日汇总。"""
    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")
    snap = fetch_snapshot(norm)
    summary = parse_diff(fetch_sp_json(norm, "Funds/lineFunds").get("diff"))
    main_net = summary.get("main_net") or snap.get("main_net")
    item = {
        "time": _today_prefix(),
        "main_net": main_net,
        "big_net": summary.get("big_net"),
        "mid_net": summary.get("mid_net"),
        "small_net": summary.get("small_net"),
        "main_net_pct": summary.get("main_net_pct"),
        "big_net_pct": summary.get("big_net_pct"),
        "mid_net_pct": summary.get("mid_net_pct"),
        "small_net_pct": summary.get("small_net_pct"),
    }
    items = [item] if main_net is not None else []
    return {
        "code": norm,
        "name": snap.get("name") or "",
        "period": "day",
        "source": "tonghuashun" if items else "",
        "count": len(items),
        "items": items,
        "note": "同花顺 stockpage 仅提供当日快照/分钟序列，daily 为当日汇总",
        "limit": min(max(int(limit or 120), 1), 120),
    }
