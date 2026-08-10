"""市场化资讯常量（东财新闻 / 研报）。"""

from __future__ import annotations

LOOKBACK_YEARS = 50
DEFAULT_FEED_DAYS = 3

EM_NEWS_URL = "https://search-api-web.eastmoney.com/search/jsonp"
EM_NEWS_CB = "jQuery35101792940631092459_1700000000000"
NEWS_PAGE_SIZE = 100
# cmsArticleWebOld：近期索引，约 10 页硬顶
NEWS_MAX_PAGES = 10
# cmsArticleWeb：归档索引，约 10 页硬顶（可含多年历史）
NEWS_ARCHIVE_MAX_PAGES = 10

EM_REPORT_URL = "https://reportapi.eastmoney.com/report/list"
REQUEST_PAUSE_SEC = 0.25

MAX_NEWS = 8000
MAX_REPORTS = 5000
