"""详情页资讯 feed 常量。"""

from __future__ import annotations

from data.core.paths import NEWS_CACHE_DIR

# 沿用 cache/news 目录，避免旧缓存键失效带来多余请求；版本号 bump 后旧文件作废
CACHE_DIR = NEWS_CACHE_DIR
CACHE_TTL_SEC = 30 * 60
CACHE_VERSION = 13

# 尽量覆盖 A 股有史以来可查区间（约 1990 起）；实际上限仍受各数据源能力约束
LOOKBACK_YEARS = 50
DEFAULT_FEED_DAYS = 3

MAX_NOTICES = 5000
MAX_NEWS = 8000
MAX_REPORTS = 5000


def pages_for_days(days: int) -> int:
    """按回溯窗口放大翻页上限，便于深历史拉全。"""
    d = max(1, int(days))
    if d <= 30:
        return 3
    if d <= 365:
        return 20
    if d <= 365 * 5:
        return 60
    if d <= 365 * 15:
        return 120
    return 200

