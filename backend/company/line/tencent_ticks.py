"""腾讯 ``stock.gtimg.cn`` 成交明细（实时逐笔，不是分时）。

接口分两步：
- ``appn=detail&action=cb``：当天分页时间段
- ``appn=detail&action=data&p=N``：第 N 页成交

每条：``序号/时间/成交价/涨跌/成交量(手)/成交额/方向``。
方向：``B`` 买盘、``S`` 卖盘、``M`` 中性。昨收来自 ``qt.gtimg.cn``。

``pos`` 与东财成交明细对齐：
- ``0``：当天全部成交（会翻页拼齐）
- 负数：最近 ``|pos|`` 笔，例如 ``-20``
- 正数：当作最近 N 笔（``20`` 等同 ``-20``）

    python company/line/tencent_ticks.py 600519
    python company/line/tencent_ticks.py 600519 --pos -20
    python company/line/tencent_ticks.py 000001 --limit 8
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from core.fmt import to_float
from core.http import get_text
from company.line.tencent_kline import resolve_symbol

logger = logging.getLogger(__name__)

_DETAIL_URL = "https://stock.gtimg.cn/data/index.php"
_QUOTE_URL = "https://qt.gtimg.cn/q="
_HEADERS = {"Referer": "https://gu.qq.com/"}
_MAX_PAGES = 80
_PAGE_WORKERS = 8

SIDE_MAP = {
    "B": (1, "buy"),
    "S": (2, "sell"),
    "M": (0, "mid"),
}

_JS_ARR_RE = re.compile(r"=\s*\[([^,]+),\"([^\"]*)\"\s*\]")


def _normalize_pos(pos: int | str | None) -> int:
    """0=当天全部；负数=最近 N 笔。返回已经规范化的整数。"""
    if pos is None or pos == "":
        return 0
    if isinstance(pos, str):
        text = pos.strip()
        if not text:
            return 0
        try:
            value = int(text)
        except ValueError as exc:
            raise ValueError("pos 须为整数，0=当天全部，负数=最近 N 笔") from exc
    else:
        value = int(pos)
    if value > 0:
        value = -value
    return value


def _parse_js_array(text: str) -> tuple[str, str] | None:
    m = _JS_ARR_RE.search(text or "")
    if not m:
        return None
    return m.group(1).strip(), m.group(2)


def _parse_row(line: str) -> dict[str, Any] | None:
    """腾讯一行：seq/time/price/change/volume/amount/side。"""
    parts = str(line).split("/")
    if len(parts) < 7:
        return None
    price = to_float(parts[2])
    if price is None:
        return None
    flag = str(parts[6]).strip().upper()
    side, label = SIDE_MAP.get(flag, (None, ""))
    seq = to_float(parts[0])
    return {
        "time": str(parts[1]).strip(),
        "price": price,
        "change": to_float(parts[3]),
        "volume": to_float(parts[4]),
        "amount": to_float(parts[5]),
        "side": side,
        "side_label": label,
        "seq": int(seq) if seq is not None else None,
    }


def _request(params: dict[str, str]) -> str:
    return get_text(
        _DETAIL_URL,
        params=params,
        headers=_HEADERS,
        timeout=12,
    )


def _page_count(symbol: str) -> tuple[str, int]:
    """返回 (YYYYMMDD, 页数)。目录失败时页数记 0。"""
    text = _request({"appn": "detail", "action": "cb", "c": symbol})
    parsed = _parse_js_array(text)
    if not parsed:
        return "", 0
    day, payload = parsed
    if not payload.strip():
        return day, 0
    return day, len(payload.split("|"))


def _fetch_page(symbol: str, page: int) -> list[dict[str, Any]]:
    text = _request(
        {"appn": "detail", "action": "data", "c": symbol, "p": str(page)}
    )
    parsed = _parse_js_array(text)
    if not parsed:
        return []
    _, payload = parsed
    if not payload.strip():
        return []
    items: list[dict[str, Any]] = []
    for line in payload.split("|"):
        row = _parse_row(line)
        if row:
            items.append(row)
    return items


def _fetch_quote_meta(symbol: str) -> dict[str, Any]:
    """顺手拿名称 / 昨收；失败就空着，不影响明细。"""
    try:
        text = get_text(
            _QUOTE_URL + symbol,
            headers=_HEADERS,
            timeout=10,
        )
    except Exception as exc:  # noqa: BLE001
        logger.info("tencent quote meta skip %s: %s", symbol, exc)
        return {}
    if '="' not in text:
        return {}
    body = text.split('="', 1)[1].rsplit('"', 1)[0]
    parts = body.split("~")
    if len(parts) < 5:
        return {}
    return {
        "name": str(parts[1] or "").strip(),
        "pre_price": to_float(parts[4]),
    }


def _take_last(items: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    if n <= 0 or len(items) <= n:
        return items
    return items[-n:]


def fetch_ticks(
    code: str,
    *,
    pos: int | str = 0,
) -> dict[str, Any]:
    """从腾讯拉当日成交明细。

    pos=0 当天全部；pos=-20（或 20）最近 20 笔。最后一条即最新成交。
    """
    symbol = resolve_symbol(code)
    if not symbol:
        raise ValueError("无效股票代码")

    want = _normalize_pos(pos)
    last_n = -want if want < 0 else 0
    digits = re.sub(r"[^0-9]", "", symbol) or symbol

    name = ""
    pre_price: float | None = None
    items: list[dict[str, Any]] = []
    last_exc: Exception | None = None
    day = ""
    pages = 0

    try:
        meta = _fetch_quote_meta(symbol)
        name = str(meta.get("name") or "")
        pre_price = meta.get("pre_price")
    except Exception as exc:  # noqa: BLE001
        logger.info("tencent ticks meta skip %s: %s", symbol, exc)

    try:
        day, pages = _page_count(symbol)
        if pages <= 0:
            pages = 1
        pages = min(pages, _MAX_PAGES)

        if last_n:
            collected: list[dict[str, Any]] = []
            for page in range(pages - 1, -1, -1):
                chunk = _fetch_page(symbol, page)
                if not chunk:
                    continue
                collected = chunk + collected
                if len(collected) >= last_n:
                    break
            items = _take_last(collected, last_n)
        else:
            with ThreadPoolExecutor(max_workers=min(_PAGE_WORKERS, pages)) as pool:
                futs = {
                    page: pool.submit(_fetch_page, symbol, page)
                    for page in range(pages)
                }
                for page in range(pages):
                    try:
                        items.extend(futs[page].result())
                    except Exception as exc:  # noqa: BLE001
                        last_exc = exc
                        logger.info(
                            "tencent ticks page skip %s p=%s: %s",
                            symbol,
                            page,
                            exc,
                        )
    except Exception as exc:  # noqa: BLE001
        last_exc = exc
        logger.info("tencent ticks skip %s: %s", symbol, exc)

    if not items and last_exc:
        raise last_exc

    last = items[-1] if items else {}
    return {
        "code": digits,
        "symbol": symbol,
        "name": name,
        "pos": str(want),
        "day": day,
        "pages": pages,
        "pre_price": pre_price,
        "last_time": last.get("time") or "",
        "last_price": last.get("price"),
        "source": "tencent" if items else "",
        "count": len(items),
        "items": items,
    }


def _print_preview(pack: dict[str, Any], preview: int) -> None:
    items = pack.get("items") or []
    print(
        f"{pack.get('symbol')} {pack.get('code')} {pack.get('name') or ''}  "
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
    parser = argparse.ArgumentParser(description="从腾讯拉取成交明细（实时逐笔）")
    parser.add_argument(
        "code",
        nargs="?",
        default="600519",
        help="代码或腾讯代码，如 600519 / sh000001 / SZ000001",
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
