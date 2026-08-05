"""通用小工具：字符串清洗、时间解析、排序键。"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd

from news.constants import LOOKBACK_YEARS


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


def lookback_start() -> datetime:
    """回溯窗口起点（约 LOOKBACK_YEARS 年，再多留几天容差）。"""
    return datetime.now() - timedelta(days=365 * LOOKBACK_YEARS + 5)


def within_lookback(item: dict[str, Any], start: datetime) -> bool:
    """条目是否落在回溯窗口内。

    没有发布时间时默认保留（避免因缺字段丢数据）。
    """
    dt = parse_time(item.get("published_at", ""))
    if dt is None:
        return True
    return dt >= start


def strip_em_tags(text: str) -> str:
    """去掉东方财富搜索结果里的 <em> 高亮标签。"""
    return re.sub(r"</?em>", "", text or "")
