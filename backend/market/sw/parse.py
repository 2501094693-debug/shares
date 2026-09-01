"""行情字符串解析：乐咕「-2.72%」/「66.43 亿」、东财哨兵值。"""

from __future__ import annotations

import re
from typing import Any

from core.fmt import to_float

_UNIT = {
    "万亿": 1e12,
    "亿": 1e8,
    "万": 1e4,
}


def bare_code(code: str) -> str:
    """``801010.SI`` / ``801010`` → ``801010``。"""
    return str(code or "").strip().split(".", 1)[0]


def parse_pct(value: Any) -> float | None:
    """百分数。``1.23%`` / ``1.23`` 都当成 1.23。"""
    if value is None:
        return None
    if isinstance(value, str):
        value = value.replace("%", "").replace(",", "").strip()
    return to_float(value)


def parse_num(value: Any) -> float | None:
    """普通数字；带 万/亿 则换成元。``66.43`` 无单位时原样返回。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return to_float(value)
    text = str(value).replace(",", "").strip()
    if not text or text in {"-", "—", "--"}:
        return None
    for unit, mul in _UNIT.items():
        if text.endswith(unit):
            number = to_float(text[: -len(unit)])
            return None if number is None else number * mul
    return to_float(text)


def parse_yi(value: Any) -> float | None:
    """市值列：乐咕成分股是「亿元」数字，无单位。"""
    number = parse_num(value)
    if number is None:
        return None
    # 已经是元（> 1e6 且不是「几个亿的小数」）时不乘
    if abs(number) >= 1e6:
        return number
    return number * 1e8


def safe_div(num: float | None, den: float | None) -> float | None:
    if num is None or den is None or den == 0:
        return None
    return num / den


def change_from_close(price: float | None, last_close: float | None) -> float | None:
    """(最新 / 昨收 - 1) × 100。"""
    ratio = safe_div(price, last_close)
    if ratio is None:
        return None
    return (ratio - 1.0) * 100.0


_SUFFIX_RE = re.compile(r"[ⅡⅢIVI2-9]+$")


def norm_name(name: str) -> str:
    """行业名对齐：去掉空白、全角数字、末尾 Ⅱ/III。"""
    text = str(name or "").strip().replace(" ", "")
    text = text.replace("Ⅱ", "").replace("Ⅲ", "").replace("III", "").replace("II", "")
    text = _SUFFIX_RE.sub("", text)
    return text.lower()
