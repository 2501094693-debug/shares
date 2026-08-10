"""公司信息披露与资讯检索（``message``）。

子包：
- ``disclosure``：上交所 / 深交所 / 北交所 / 巨潮公告与监管问询
- ``press``：七家指定披露媒体相关报道
- ``market``：东财媒体新闻与机构研报
- ``taxonomy``：统一 category / source_tier / subcategory 分类
- ``profile``：按类汇总的公司信息画像（``query_company_profile``）
- ``feed``：详情页资讯（``collect_company_messages`` → ``/api/stocks/news``）
"""

from __future__ import annotations

from .disclosure import (
    query_announcements,
    query_company_messages,
    query_multi,
    query_regulatory,
)
from .feed import collect_company_messages, collect_important_news
from .press import query_press, query_press_flat
from .profile import query_company_profile
from .taxonomy import classify_item

__all__ = [
    "query_announcements",
    "query_regulatory",
    "query_company_messages",
    "query_multi",
    "query_press",
    "query_press_flat",
    "query_company_profile",
    "collect_company_messages",
    "collect_important_news",
    "classify_item",
]
