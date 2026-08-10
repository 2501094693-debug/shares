"""指定披露媒体（七报七网）新闻检索。

主通道：东方财富新闻索引按媒体署名筛选。
辅通道：部分官网直连搜索（可得则合并）。
"""

from __future__ import annotations

from .constants import OUTLETS, OUTLET_BY_ID
from .query import query_press, query_press_flat

__all__ = [
    "OUTLETS",
    "OUTLET_BY_ID",
    "query_press",
    "query_press_flat",
]
