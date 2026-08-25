"""行情数字 → 前端展示字符串。

数据源给的是原始数字（元、手、百分比），页面要的是「12.34 亿」「1.2%」。
空值统一成 ``""``，调用方可以直接塞进 dict，不必再判 None。

``to_float`` 是所有格式化的入口：None / "-" / NaN / 东财哨兵值（≤ -1e10）都视为缺失。
"""

from __future__ import annotations

from typing import Any


def to_float(value: Any) -> float | None:
    """宽松转 float。无法解析或明显是哨兵值时返回 None。"""
    if value is None or value == "" or value == "-":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    # 东财部分字段用极大负数表示「无数据」
    if number <= -1e10:
        return None
    return number


def fmt_price(value: Any, digits: int = 2) -> str:
    """价格：``12.34``。"""
    number = to_float(value)
    if number is None:
        return ""
    return f"{number:.{digits}f}"


def fmt_pct(value: Any, digits: int = 2) -> str:
    """百分比：``1.23%``。入参已经是百分数，不再 ×100。"""
    number = to_float(value)
    if number is None:
        return ""
    return f"{number:.{digits}f}%"


def fmt_signed(value: Any, digits: int = 2) -> str:
    """带符号的普通数字（涨跌额、PE 等），不加单位。"""
    number = to_float(value)
    if number is None:
        return ""
    return f"{number:.{digits}f}"


def fmt_yi_wan(value: Any, *, unit_yi: bool = False) -> str:
    """金额（元）→ 亿 / 万。

    ``unit_yi=True`` 时强制用亿（总市值、流通市值对齐东财盘口）。
    """
    number = to_float(value)
    if number is None:
        return ""
    abs_n = abs(number)
    sign = "-" if number < 0 else ""
    if unit_yi or abs_n >= 1e8:
        text = f"{abs_n / 1e8:.2f}".rstrip("0").rstrip(".")
        return f"{sign}{text}亿"
    if abs_n >= 1e4:
        text = f"{abs_n / 1e4:.2f}".rstrip("0").rstrip(".")
        return f"{sign}{text}万"
    return f"{sign}{abs_n:.0f}"


def fmt_shares(value: Any) -> str:
    """股数 → 亿 / 万。"""
    number = to_float(value)
    if number is None:
        return ""
    abs_n = abs(number)
    if abs_n >= 1e8:
        text = f"{abs_n / 1e8:.2f}".rstrip("0").rstrip(".")
        return f"{text}亿"
    if abs_n >= 1e4:
        text = f"{abs_n / 1e4:.2f}".rstrip("0").rstrip(".")
        return f"{text}万"
    return f"{abs_n:.0f}"


def fmt_volume_hands(value: Any) -> str:
    """成交量（手）→ 超过 1 万手写成 ``x.x万``。"""
    number = to_float(value)
    if number is None:
        return ""
    abs_n = abs(number)
    if abs_n >= 1e4:
        return f"{abs_n / 1e4:.1f}万".replace(".0万", "万")
    return f"{abs_n:.0f}"


def fmt_list_date(value: Any) -> str:
    """上市日：``20200101`` → ``2020-01-01``；已是 ``YYYY-MM-DD`` 则截前 10 位。"""
    text = str(value or "").strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    return text


def pct_change(current: float, base: float) -> str:
    """相对涨幅：(current / base - 1) × 100，再格式化成百分比。"""
    if base == 0:
        return ""
    return fmt_pct((current / base - 1.0) * 100)


def drop_empty(fields: dict[str, Any]) -> dict[str, Any]:
    """去掉 None / 空字符串，避免把空洞字段覆盖乐咕兜底值。"""
    return {key: value for key, value in fields.items() if value not in (None, "")}
