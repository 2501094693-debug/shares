"""iFinD 逐笔委托：用高频序列自定义指标拉取。

标准数据接口手册只列出成交侧 ``zb_*``，没有委托字段。官方 FAQ 写明逐笔要
DataFeed（实时）或数据库产品（历史）。若你的账号在超级命令里能生成委托指标，
把指标名写到 ``IFIND_ORDER_INDICATORS``（分号或逗号分隔）。

默认尝试 ``wt_time;wt_price;wt_volume;wt_bs;wt_type``。指标不存在时接口会报错。

    python -m company.line.original 600519 --kind orders
    python -m company.line.original.orders 000001 --pos -20
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[3]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from core.codes import normalize_code, ths_code
from core.fmt import to_float

from company.line.original._common import SOURCE, cell_time, map_side, normalize_pos, session_window
from company.line.original.client import IFindError, high_frequency, tables

logger = logging.getLogger(__name__)

DEFAULT_ORDER_INDICATORS = "wt_time;wt_price;wt_volume;wt_bs;wt_type"

TYPE_LABEL = {
    "add": "add",
    "cancel": "cancel",
    "delete": "cancel",
    "new": "add",
    "a": "add",
    "d": "cancel",
    "c": "cancel",
}


def _order_indicators() -> list[str]:
    raw = (os.environ.get("IFIND_ORDER_INDICATORS") or "").strip() or DEFAULT_ORDER_INDICATORS
    return [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]


def _pick(row: dict[str, Any], *keys: str) -> Any:
    lower = {str(k).lower(): v for k, v in row.items()}
    for key in keys:
        if key in row and row[key] not in {None, ""}:
            return row[key]
        alt = lower.get(key.lower())
        if alt not in {None, ""}:
            return alt
    return None


def _map_order_type(raw: Any) -> tuple[str, str]:
    text = str(raw or "").strip()
    if not text:
        return "", ""
    key = text.lower()
    if "撤" in text or "删" in text or TYPE_LABEL.get(key) == "cancel":
        return "cancel", "cancel"
    if "新" in text or "增" in text or "报" in text or key in {"1", "a", "add", "new"}:
        return "add", "add"
    mapped = TYPE_LABEL.get(key, "")
    return str(raw), mapped


def _parse_row(row: dict[str, Any]) -> dict[str, Any] | None:
    price = to_float(_pick(row, "wt_price", "price", "zb_price", "order_price"))
    volume = to_float(_pick(row, "wt_volume", "volume", "zb_volume", "order_volume", "qty"))
    time_s = cell_time(_pick(row, "wt_time", "time", "zb_time", "datetime"))
    if not time_s and price is None and volume is None:
        return None
    side, side_label = map_side(_pick(row, "wt_bs", "bs", "zb_type", "side", "direction"))
    order_type, type_label = _map_order_type(_pick(row, "wt_type", "type", "order_type", "entrustType"))
    seq = _pick(row, "wt_seq", "seq", "order_no", "entrustNo", "orderno")
    seq_n = to_float(seq)
    return {
        "time": time_s,
        "price": price,
        "volume": volume,
        "side": side,
        "side_label": side_label,
        "order_type": order_type,
        "type_label": type_label,
        "seq": int(seq_n) if seq_n is not None else seq,
    }


def fetch_orders(
    code: str,
    *,
    pos: int | str = 0,
    start: str = "",
    end: str = "",
    max_points: int = 100000,
) -> dict[str, Any]:
    """从 iFinD 拉一段逐笔委托（取决于账号是否开通对应指标）。"""
    symbol = ths_code(code)
    if not symbol:
        raise ValueError("无效股票代码")
    pos_n = normalize_pos(pos)
    begin, finish = session_window(start, end)
    indicators = _order_indicators()
    try:
        payload = high_frequency(
            symbol,
            indicators,
            start=begin,
            end=finish,
            max_points=max_points,
        )
    except IFindError as exc:
        hint = (
            "iFinD 标准数据接口通常不含逐笔委托。"
            "请在超级命令里生成委托指标，写入 IFIND_ORDER_INDICATORS；"
            "实时完整委托流需要 DataFeed Level-2。"
        )
        raise IFindError(f"{exc} {hint}", errorcode=exc.errorcode) from exc

    parsed: list[dict[str, Any]] = []
    for row in tables(payload):
        item = _parse_row(row)
        if item:
            parsed.append(item)
    if pos_n < 0:
        parsed = parsed[pos_n:]
    last = parsed[-1] if parsed else {}
    return {
        "code": normalize_code(code) or symbol,
        "thscode": symbol,
        "pos": str(pos_n),
        "start": begin,
        "end": finish,
        "indicators": ";".join(indicators),
        "last_time": last.get("time") or "",
        "last_price": last.get("price"),
        "source": SOURCE if parsed else "",
        "kind": "order",
        "count": len(parsed),
        "items": parsed,
    }


def _print_preview(pack: dict[str, Any], preview: int) -> None:
    items = pack.get("items") or []
    print(
        f"{pack.get('thscode')}  "
        f"pos={pack.get('pos')}  "
        f"indicators={pack.get('indicators')}  "
        f"last={pack.get('last_time')} {pack.get('last_price')}  "
        f"count={pack.get('count')}  source={pack.get('source') or '-'}"
    )
    if not items:
        print("  (empty)")
        return
    shown = items[-preview:] if preview > 0 else items
    print(json.dumps(shown, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="从 iFinD 拉取逐笔委托")
    parser.add_argument("code", nargs="?", default="600519", help="股票代码，如 600519")
    parser.add_argument("--pos", default="0", help="0=当天全部；-20 或 20=最近 20 笔")
    parser.add_argument("--start", default="", help="开始时间 YYYY-MM-DD[ HH:MM:SS]")
    parser.add_argument("--end", default="", help="结束时间 YYYY-MM-DD[ HH:MM:SS]")
    parser.add_argument("--limit", type=int, default=5, help="预览最近笔数")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        pack = fetch_orders(
            args.code,
            pos=args.pos,
            start=args.start,
            end=args.end,
        )
    except (IFindError, ValueError) as exc:
        print(exc)
        return 1
    _print_preview(pack, args.limit)
    return 0 if pack.get("source") else 1


if __name__ == "__main__":
    raise SystemExit(main())
