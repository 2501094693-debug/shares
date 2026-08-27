"""iFinD 逐笔成交：高频序列 ``zb_time;zb_price;zb_volume;zb_type``。

这是数据接口手册里的「逐笔行情」指标，不是交易所原始逐笔回报。
官方 FAQ 称部分账号已不再开放逐笔，失败时看 errorcode / errmsg。

量是接口原值（一般为股）。``pos`` 与东财成交明细对齐：0=当天全部，负数=最近 N 笔。

    python -m company.line.original 600519
    python -m company.line.original.ticks 600519 --pos -20
"""

from __future__ import annotations

import argparse
import json
import logging
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

TICK_INDICATORS = ("zb_time", "zb_price", "zb_volume", "zb_type")


def _row_time(row: dict[str, Any]) -> str:
    for key in ("zb_time", "time", "datetime"):
        text = cell_time(row.get(key))
        if text:
            return text
    return ""


def _parse_row(row: dict[str, Any]) -> dict[str, Any] | None:
    price = to_float(row.get("zb_price") if row.get("zb_price") is not None else row.get("price"))
    if price is None:
        return None
    side, label = map_side(row.get("zb_type") if row.get("zb_type") is not None else row.get("type"))
    volume = to_float(row.get("zb_volume") if row.get("zb_volume") is not None else row.get("volume"))
    return {
        "time": _row_time(row),
        "price": price,
        "volume": volume,
        "side": side,
        "side_label": label,
        "type": row.get("zb_type") if row.get("zb_type") is not None else row.get("type"),
    }


def fetch_transactions(
    code: str,
    *,
    pos: int | str = 0,
    start: str = "",
    end: str = "",
    max_points: int = 100000,
) -> dict[str, Any]:
    """从 iFinD 拉一段逐笔成交。"""
    symbol = ths_code(code)
    if not symbol:
        raise ValueError("无效股票代码")
    pos_n = normalize_pos(pos)
    begin, finish = session_window(start, end)
    payload = high_frequency(
        symbol,
        TICK_INDICATORS,
        start=begin,
        end=finish,
        max_points=max_points,
    )
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
        "last_time": last.get("time") or "",
        "last_price": last.get("price"),
        "source": SOURCE if parsed else "",
        "kind": "transaction",
        "count": len(parsed),
        "items": parsed,
    }


def _print_preview(pack: dict[str, Any], preview: int) -> None:
    items = pack.get("items") or []
    print(
        f"{pack.get('thscode')}  "
        f"pos={pack.get('pos')}  "
        f"last={pack.get('last_time')} {pack.get('last_price')}  "
        f"count={pack.get('count')}  source={pack.get('source') or '-'}"
    )
    if not items:
        print("  (empty)")
        return
    shown = items[-preview:] if preview > 0 else items
    print(json.dumps(shown, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="从 iFinD 拉取逐笔成交")
    parser.add_argument("code", nargs="?", default="600519", help="股票代码，如 600519")
    parser.add_argument("--pos", default="0", help="0=当天全部；-20 或 20=最近 20 笔")
    parser.add_argument("--start", default="", help="开始时间 YYYY-MM-DD[ HH:MM:SS]")
    parser.add_argument("--end", default="", help="结束时间 YYYY-MM-DD[ HH:MM:SS]")
    parser.add_argument("--limit", type=int, default=5, help="预览最近笔数")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        pack = fetch_transactions(
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
