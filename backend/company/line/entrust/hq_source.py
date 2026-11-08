"""同花顺 HQ 游客通道：``depth`` 五档兜底。

不依赖扫码登录；字段号来自抓包（买 1–3 = 24/25…28/29，卖 1–3 = 30/31…34/35，
买/卖 4–5 = 150–157）。仅有各档总量，无委托单细则。

注意：``depth`` 返回的字段 ``6`` 是昨收，不是现价（跌停日最明显：6=昨收，
成交价在卖一）。现价由 ``fill_book_last_price`` 用腾讯行情 / 单边盘口补齐。
"""

from __future__ import annotations

import logging
from typing import Any

from core.codes import normalize_code
from core.fmt import to_float

from company.line.entrust.models import empty_pack, fill_book_last_price, normalize_level

logger = logging.getLogger(__name__)

# (side, level, price_field, volume_field)
_DEPTH_FIELDS: tuple[tuple[str, int, str, str], ...] = (
    ("bid", 1, "24", "25"),
    ("bid", 2, "26", "27"),
    ("bid", 3, "28", "29"),
    ("bid", 4, "150", "151"),
    ("bid", 5, "154", "155"),
    ("ask", 1, "30", "31"),
    ("ask", 2, "32", "33"),
    ("ask", 3, "34", "35"),
    ("ask", 4, "152", "153"),
    ("ask", 5, "156", "157"),
)


def _cell(row: dict[str, Any], key: str) -> Any:
    if key in row:
        return row.get(key)
    try:
        return row.get(int(key))
    except (TypeError, ValueError):
        return None


def fetch_order_book(code: str) -> dict[str, Any]:
    """HQ ``depth`` → 统一 book 结构。"""
    from company.statistics.fundflow.tonghuashun import hq as _hq

    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")
    security = _hq.hq_security(norm)
    if not security:
        raise ValueError("无法映射同花顺证券代码")

    client = _hq._client
    client.connect()
    body = client._invoke("depth", {"code": security}, 512 * 1024)
    err = str(body.get("err_info") or "")
    if err:
        raise RuntimeError(err)
    payload = body.get("payload") if isinstance(body.get("payload"), dict) else body
    rows = payload.get("result") if isinstance(payload, dict) else None
    row = next((item for item in rows or [] if isinstance(item, dict)), None)

    pack = empty_pack(norm)
    pack["source"] = "ths_hq:depth"
    if not row:
        pack["notes"].append("HQ depth 返回空")
        return pack

    bids: list[dict[str, Any]] = []
    asks: list[dict[str, Any]] = []
    for side, level, px_key, vol_key in _DEPTH_FIELDS:
        parsed = normalize_level(
            level=level,
            price=_cell(row, px_key),
            volume=_cell(row, vol_key),
        )
        if not parsed:
            continue
        (bids if side == "bid" else asks).append(parsed)

    # 字段 6 = 昨收（不是现价）；现价见 fill_book_last_price
    pre_close = to_float(_cell(row, "6"))
    pack["book"] = {
        "depth": max(len(bids), len(asks)),
        "last": None,
        "pre_close": pre_close,
        "bids": bids,
        "asks": asks,
    }
    fill_book_last_price(norm, pack["book"])
    pack["notes"].append("HQ 游客 depth 仅五档总量，无 Level-2 委托单细则")
    return pack
