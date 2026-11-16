"""同花顺当日分价表（``thsdk.list_security_price_volume_levels``，需实盘扫码登录）。

把当天已成交量按成交价汇总：每个价位一行，含总量 / 内外盘 / 笔数。
这是「价位直方图」，不是买卖队列里的挂单明细，也不是逐笔时间线。

    python -m company.line.tonghuashun.price_levels 600519
    python -m company.line.tonghuashun.price_levels 600519 --limit 10
    python -m company.line.tonghuashun.price_levels 600519 --around 1450 --span 5
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[3]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from core.codes import normalize_code
from core.fmt import to_float

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


def fetch_price_levels(
    code: str,
    *,
    timeout: float | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """拉取当日分价表。

    返回 ``(method, items)``，``items`` 按 ``price`` 升序。
    每条为 ``{price/volume/volume_lots/in_volume/out_volume/
    transaction_count/out_volume_rate}``，``volume`` 单位为股。
    """
    import thsdk
    from company.line.tonghuashun import auth as _ths_auth

    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")
    if not _ths_auth.ensure(timeout=3):
        raise RuntimeError("THS_NEED_QRCODE:同花顺需扫码登录，前端打开扫码弹窗后重试")

    security = _hq_security(norm)
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
        raise RuntimeError(f"{norm} 分价表为空（非交易日或无权限）")
    return "thsdk:price_volume_levels", items


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

    return {
        "code": norm,
        "period": "price_levels",
        "source": "tonghuashun",
        "method": method,
        "count": len(view),
        "total_count": len(items),
        "summary": summary,
        "items": view,
        "notes": ["分价表为当日各价位已成交汇总，不是买卖队列挂单明细"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="同花顺当日分价表（需实盘登录）")
    parser.add_argument("code", help="股票代码，如 600519")
    parser.add_argument("--limit", type=int, default=10, help="预览档数，0=全部")
    parser.add_argument("--around", type=float, default=None, help="只看某价附近，如 1450")
    parser.add_argument(
        "--span",
        type=float,
        default=5.0,
        help="配合 --around 的半宽（元），默认 5",
    )
    args = parser.parse_args()
    pack = fetch_price_levels_pack(
        args.code,
        around=args.around,
        span=args.span,
        limit=args.limit,
    )
    print(json.dumps(pack, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
