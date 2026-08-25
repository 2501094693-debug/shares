"""东财 ``/api/qt/stock/details/get`` 成交明细（实时逐笔，不是分时）。

和 ``trends2`` 分时的区别：分时是每分钟一个点；这里是每一笔成交一个点。
盘中多次请求即可跟上最新成交。HTTP 轮询，没有对外推送。

``pos``：
- ``0``：当天全部成交
- 负数：最近 ``|pos|`` 笔，例如 ``-20``
- 正数：当作最近 N 笔（``20`` 等同 ``-20``）

每条 ``details``：``时间,成交价,成交量(手),笔数,方向``。
方向：``1`` 买盘、``2`` 卖盘、``4`` 集合竞价。昨收在 ``prePrice``。

    python company/line/eastmoney_ticks.py 600519
    python company/line/eastmoney_ticks.py 600519 --pos -20
    python company/line/eastmoney_ticks.py 000001 --limit 8
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from core.codes import normalize_code
from core.fmt import to_float
from core.http import get_json
from company.line.eastmoney_kline import resolve_secid

logger = logging.getLogger(__name__)

# 成交明细是实时接口，delay / 编号节点优先；his 经常没有
_HOSTS = (
    "https://push2delay.eastmoney.com",
    "https://push2.eastmoney.com",
    "https://82.push2.eastmoney.com",
    "https://71.push2.eastmoney.com",
)

_HEADERS = {"Referer": "https://quote.eastmoney.com/"}
_UT = "fa5fd1943c7b386f172d6893dbfba10b"
_FIELDS1 = "f1,f2,f3,f4"
_FIELDS2 = "f51,f52,f53,f54,f55"

SIDE_LABEL = {
    1: "buy",
    2: "sell",
    4: "auction",
}


def _normalize_pos(pos: int | str | None) -> str:
    if pos is None or pos == "":
        return "0"
    if isinstance(pos, str):
        text = pos.strip()
        if not text:
            return "0"
        try:
            value = int(text)
        except ValueError as exc:
            raise ValueError("pos 须为整数，0=当天全部，负数=最近 N 笔") from exc
    else:
        value = int(pos)
    if value > 0:
        value = -value
    return str(value)


def _parse_row(line: str) -> dict[str, Any] | None:
    """东财 details 一行：time,price,volume,count,side。"""
    parts = str(line).split(",")
    if len(parts) < 3:
        return None
    price = to_float(parts[1])
    if price is None:
        return None
    side = None
    if len(parts) > 4:
        raw = str(parts[4]).strip()
        if raw.isdigit() or (raw.startswith("-") and raw[1:].isdigit()):
            side = int(raw)
    return {
        "time": str(parts[0]).strip(),
        "price": price,
        "volume": to_float(parts[2]),
        "count": to_float(parts[3]) if len(parts) > 3 else None,
        "side": side,
        "side_label": SIDE_LABEL.get(side or -1, ""),
    }


def fetch_ticks(
    code: str,
    *,
    pos: int | str = 0,
) -> dict[str, Any]:
    """从东财拉当日成交明细。

    pos=0 当天全部；pos=-20（或 20）最近 20 笔。最后一条即最新成交。
    """
    sid = resolve_secid(code)
    if not sid:
        raise ValueError("无效股票代码")

    pos_s = _normalize_pos(pos)
    params = {
        "secid": sid,
        "fields1": _FIELDS1,
        "fields2": _FIELDS2,
        "pos": pos_s,
        "ut": _UT,
    }

    market: int | None = None
    decimal: int | None = None
    pre_price: float | None = None
    out_code = normalize_code(code) or sid
    items: list[dict[str, Any]] = []
    last_exc: Exception | None = None

    for host in _HOSTS:
        try:
            payload = get_json(
                f"{host}/api/qt/stock/details/get",
                params=params,
                headers=_HEADERS,
                timeout=12,
            )
            data = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(data, dict):
                continue
            rows = data.get("details") or []
            parsed: list[dict[str, Any]] = []
            for line in rows:
                row = _parse_row(str(line))
                if row:
                    parsed.append(row)
            if not parsed:
                continue
            items = parsed
            out_code = str(data.get("code") or out_code).strip()
            market = data.get("market")
            decimal = data.get("decimal")
            pre_price = to_float(data.get("prePrice"))
            break
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.info("eastmoney ticks skip %s %s: %s", sid, host, exc)
            continue

    if not items and last_exc:
        raise last_exc

    last = items[-1] if items else {}
    return {
        "code": out_code,
        "secid": sid,
        "market": market,
        "decimal": decimal,
        "pos": pos_s,
        "pre_price": pre_price,
        "last_time": last.get("time") or "",
        "last_price": last.get("price"),
        "source": "eastmoney" if items else "",
        "count": len(items),
        "items": items,
    }


def _print_preview(pack: dict[str, Any], preview: int) -> None:
    items = pack.get("items") or []
    print(
        f"{pack.get('secid')} {pack.get('code')}  "
        f"pos={pack.get('pos')}  "
        f"pre_price={pack.get('pre_price')}  "
        f"last={pack.get('last_time')} {pack.get('last_price')}  "
        f"count={pack.get('count')}  source={pack.get('source') or '-'}"
    )
    if not items:
        print("  (empty)")
        return
    shown = items[-preview:] if preview > 0 else items
    print(json.dumps(shown, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="从东财拉取成交明细（实时逐笔）")
    parser.add_argument(
        "code",
        nargs="?",
        default="600519",
        help="代码或 secid，如 600519 / SH000001 / 1.000001",
    )
    parser.add_argument(
        "--pos",
        default="0",
        help="0=当天全部；-20 或 20=最近 20 笔",
    )
    parser.add_argument("--limit", type=int, default=5, help="预览最近笔数")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    pack = fetch_ticks(args.code, pos=args.pos)
    _print_preview(pack, args.limit)
    return 0 if pack.get("source") else 1


if __name__ == "__main__":
    raise SystemExit(main())
