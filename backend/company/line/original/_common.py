"""iFinD 逐笔共用：时间窗口、pos、买卖方向。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from core.fmt import to_float

TZ_CN = timezone(timedelta(hours=8))
SOURCE = "ifind"

SIDE_LABEL = {
    1: "buy",
    2: "sell",
    4: "auction",
    0: "mid",
}


def normalize_pos(pos: int | str | None) -> int:
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


def session_window(start: str = "", end: str = "") -> tuple[str, str]:
    now = datetime.now(TZ_CN)
    day = now.strftime("%Y-%m-%d")
    begin = (start or "").strip() or f"{day} 09:15:00"
    finish = (end or "").strip() or f"{day} 15:15:00"
    if len(begin) == 10:
        begin = f"{begin} 09:15:00"
    if len(finish) == 10:
        finish = f"{finish} 15:15:00"
    return begin, finish


def map_side(raw: Any) -> tuple[int | None, str]:
    text = str(raw or "").strip()
    if not text:
        return None, ""
    key = text.lower()
    if key in {"1", "b", "buy", "bid"} or "买" in text:
        return 1, "buy"
    if key in {"2", "s", "sell", "ask"} or "卖" in text:
        return 2, "sell"
    if key in {"4"} or "竞价" in text or "集合" in text:
        return 4, "auction"
    if key in {"0", "m", "mid"} or "中性" in text:
        return 0, "mid"
    number = to_float(raw)
    if number is None:
        return None, ""
    side = int(number)
    return side, SIDE_LABEL.get(side, "")


def cell_time(value: Any) -> str:
    if value is None or value == "":
        return ""
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].replace(" ", "").replace(":", "").replace("-", "").isdigit():
        text = text[:-2]
    return text
