"""通用小工具：字符串清洗、时间解析、排序键。"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd

from .constants import LOOKBACK_YEARS


def safe_str(value: Any) -> str:
    """把任意值转成干净字符串；None / NaN / 日期都做特殊处理。"""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return str(value).strip()


def parse_time(value: Any) -> datetime | None:
    """尽量把各种时间字段解析成 datetime；失败返回 None。"""
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())

    text = safe_str(value)
    if not text:
        return None

    # 常见 A 股资讯时间格式，按长度截断后尝试
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y-%m-%d",
        "%Y/%m/%d",
    ):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            continue
    return None


def sort_key(item: dict[str, Any]) -> tuple[int, float]:
    """排序键：有发布时间的靠前，且越新越靠前；无时间的排最后。"""
    dt = parse_time(item.get("published_at", ""))
    if dt is None:
        return (1, 0.0)
    return (0, -dt.timestamp())


def lookback_start(days: int | None = None) -> datetime:
    """回溯窗口起点。

    days 为 None 时使用 LOOKBACK_YEARS（约两年）；否则用指定天数。
    """
    if days is None:
        days = 365 * LOOKBACK_YEARS + 5
    return datetime.now() - timedelta(days=max(1, int(days)))


def full_lookback_days() -> int:
    return 365 * LOOKBACK_YEARS + 5


def within_lookback(
    item: dict[str, Any],
    start: datetime,
    *,
    require_time: bool = False,
) -> bool:
    """条目是否落在回溯窗口内。

    require_time=False（默认）：无发布时间时保留。
    require_time=True（短窗口如近 3 天）：无发布时间则丢弃，避免脏数据。
    """
    dt = parse_time(item.get("published_at", ""))
    if dt is None:
        return not require_time
    return dt >= start


def strip_em_tags(text: str) -> str:
    """去掉东方财富搜索结果里的 <em> 高亮标签。"""
    return re.sub(r"</?em>", "", text or "")
