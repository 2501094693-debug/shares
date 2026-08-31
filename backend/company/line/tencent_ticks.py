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

# v_xxx=[字段,"payload"] ，目录和分页都是这个壳。
_JS_ARR_RE = re.compile(r"=\s*\[([^,]+),\"([^\"]*)\"\s*\]")


def _js_payload(text: str) -> tuple[str, str] | None:
    m = _JS_ARR_RE.search(text or "")
    if not m:
        return None
    return m.group(1).strip(), m.group(2)


# ---------------------------------------------------------------------------
# 1. 参数计算
# ---------------------------------------------------------------------------

def _normalize_pos(pos: int | str | None) -> int:
    """0=当天全部；负数=最近 N 笔。正数会收成负数。"""
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


def _params(code: str, pos: int | str) -> dict[str, Any]:
    """规范化入参。last_n>0 表示只要最近 N 笔，否则拉当天全部。"""
    symbol = resolve_symbol(code)
    if not symbol:
        raise ValueError("无效股票代码")
    want = _normalize_pos(pos)
    return {
        "symbol": symbol,
        "code": re.sub(r"[^0-9]", "", symbol) or symbol,
        "pos": want,
        "last_n": -want if want < 0 else 0,
    }


# ---------------------------------------------------------------------------
# 2. 请求数据
# ---------------------------------------------------------------------------

def _get_detail(query: dict[str, str]) -> str:
    return get_text(_DETAIL_URL, params=query, headers=_HEADERS, timeout=12)


def _catalog_meta(text: str) -> tuple[str, int]:
    """目录页：返回 (YYYYMMDD, 页数)。解析失败时页数记 0。"""
    parsed = _js_payload(text)
    if not parsed:
        return "", 0
    day, payload = parsed
    if not payload.strip():
        return day, 0
    return day, len(payload.split("|"))


def _payload_n(text: str) -> int:
    """一页里大约有多少笔，用来决定最近 N 笔还要不要再翻一页。"""
    parsed = _js_payload(text)
    if not parsed or not parsed[1].strip():
        return 0
    return len(parsed[1].split("|"))


def _request(params: dict[str, Any]) -> dict[str, Any]:
    """拉齐原始文本：行情、目录、各页成交。"""
    symbol = params["symbol"]
    last_exc: Exception | None = None
    quote_text = ""
    catalog_text = ""
    page_texts: list[str] = []
    day = ""
    pages = 0

    try:
        quote_text = get_text(_QUOTE_URL + symbol, headers=_HEADERS, timeout=10)
    except Exception as exc:  # noqa: BLE001
        logger.info("tencent quote meta skip %s: %s", symbol, exc)

    try:
        catalog_text = _get_detail({"appn": "detail", "action": "cb", "c": symbol})
        day, pages = _catalog_meta(catalog_text)
        if pages <= 0:
            pages = 1
        pages = min(pages, _MAX_PAGES)

        if params["last_n"]:
            # 从最后一页往前翻，凑够最近 N 笔就停，少打几枪。
            n = 0
            for page in range(pages - 1, -1, -1):
                try:
                    text = _get_detail(
                        {"appn": "detail", "action": "data", "c": symbol, "p": str(page)}
                    )
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    logger.info("tencent ticks page skip %s p=%s: %s", symbol, page, exc)
                    continue
                page_texts.insert(0, text)
                n += _payload_n(text)
                if n >= params["last_n"]:
                    break
        else:
            with ThreadPoolExecutor(max_workers=min(_PAGE_WORKERS, pages)) as pool:
                futs = {
                    page: pool.submit(
                        _get_detail,
                        {"appn": "detail", "action": "data", "c": symbol, "p": str(page)},
                    )
                    for page in range(pages)
                }
                for page in range(pages):
                    try:
                        page_texts.append(futs[page].result())
                    except Exception as exc:  # noqa: BLE001
                        last_exc = exc
                        logger.info("tencent ticks page skip %s p=%s: %s", symbol, page, exc)
    except Exception as exc:  # noqa: BLE001
        last_exc = exc
        logger.info("tencent ticks skip %s: %s", symbol, exc)

    return {
        "quote_text": quote_text,
        "catalog_text": catalog_text,
        "page_texts": page_texts,
        "day": day,
        "pages": pages,
        "last_exc": last_exc,
    }


# ---------------------------------------------------------------------------
# 3. 数据解析
# ---------------------------------------------------------------------------

def _parse_quote(text: str) -> dict[str, Any]:
    """qt.gtimg.cn 一行：名称在 ~ 分隔的下标 1，昨收在下标 4。"""
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


def _parse_page(text: str) -> list[dict[str, Any]]:
    parsed = _js_payload(text)
    if not parsed or not parsed[1].strip():
        return []
    items: list[dict[str, Any]] = []
    for line in parsed[1].split("|"):
        row = _parse_row(line)
        if row:
            items.append(row)
    return items


def _parse(raw: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """把行情 + 各页成交文本收成统一逐笔包。"""
    meta = _parse_quote(raw.get("quote_text") or "")
    items: list[dict[str, Any]] = []
    for text in raw.get("page_texts") or []:
        items.extend(_parse_page(text))

    last_n = params["last_n"]
    if last_n and len(items) > last_n:
        items = items[-last_n:]

    last_exc = raw.get("last_exc")
    if not items and last_exc:
        raise last_exc

    last = items[-1] if items else {}
    return {
        "code": params["code"],
        "symbol": params["symbol"],
        "name": str(meta.get("name") or ""),
        "pos": str(params["pos"]),
        "day": raw.get("day") or "",
        "pages": raw.get("pages") or 0,
        "pre_price": meta.get("pre_price"),
        "last_time": last.get("time") or "",
        "last_price": last.get("price"),
        "source": "tencent" if items else "",
        "count": len(items),
        "items": items,
    }


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def fetch_ticks(
    code: str,
    *,
    pos: int | str = 0,
) -> dict[str, Any]:
    """从腾讯拉当日成交明细。

    pos=0 当天全部；pos=-20（或 20）最近 20 笔。最后一条即最新成交。
    """
    params = _params(code, pos)
    raw = _request(params)
    return _parse(raw, params)


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
    parser.add_argument("--pos", default="0", help="0=当天全部；-20 或 20=最近 20 笔")
    parser.add_argument("--limit", type=int, default=5, help="预览最近笔数")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    pack = fetch_ticks(args.code, pos=args.pos)
    _print_preview(pack, args.limit)
    return 0 if pack.get("source") else 1


if __name__ == "__main__":
    raise SystemExit(main())
