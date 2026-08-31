"""个股资讯：采集源 + 详情页 / 画像。

采集源：
  official     巨潮 / 交易所 / 七网
  platforms    东方财富 / 同花顺 / 雪球

根目录只做集成：
  query      公告 / 监管 / 七网 / 市场新闻 / 研报
  feed       详情页分组 → /api/stocks/news
  profile    分类画像 → /api/stocks/profile-messages
  taxonomy   category / source_tier / subcategory
  _items     条目规范化
  cache      磁盘缓存
"""

from company.news.feed import VALID_KINDS, collect_company_messages
from company.news.profile import query_company_profile
from company.news.query import (
    query_announcements,
    query_company_messages,
    query_market_news,
    query_press,
    query_regulatory,
    query_reports,
)
from company.news.taxonomy import ALL_SECTIONS, DEFAULT_SECTIONS, classify_item

__all__ = [
    "ALL_SECTIONS",
    "DEFAULT_SECTIONS",
    "VALID_KINDS",
    "classify_item",
    "collect_company_messages",
    "query_announcements",
    "query_company_messages",
    "query_company_profile",
    "query_market_news",
    "query_press",
    "query_regulatory",
    "query_reports",
]
