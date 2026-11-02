"""全市场区间评估筛选：默认参数与并发。"""

from __future__ import annotations

from company.analysis.line.evaluate.core import DEFAULT_BAND
from company.analysis.line.evaluate.service import (
    DEFAULT_INDEX,
    DEFAULT_LOOKBACK_DAYS,
)

DEFAULT_FACTOR = "close"
# find_max_range 已是 O(n)，批量主要卡在日线 IO；提高默认并发
DEFAULT_WORKERS = 16
MIN_WORKERS = 1
MAX_WORKERS = 32

# 进度回调节流：每完成 N 只推一次，避免锁竞争
PROGRESS_EVERY = 20

# 落盘键版本，算法变更后与旧缓存隔离（e7：谷序列改为最近 900 交易日）
CACHE_TAG = "e7"

ALLOWED_BANDS = (0.05, 0.09, 0.12)
ALLOWED_FACTORS = ("open", "high", "low", "close")
ALLOWED_INDEXES = ("000001", "399001", "000300")

__all__ = [
    "ALLOWED_BANDS",
    "ALLOWED_FACTORS",
    "ALLOWED_INDEXES",
    "CACHE_TAG",
    "DEFAULT_BAND",
    "DEFAULT_FACTOR",
    "DEFAULT_INDEX",
    "DEFAULT_LOOKBACK_DAYS",
    "DEFAULT_WORKERS",
    "MAX_WORKERS",
    "MIN_WORKERS",
    "PROGRESS_EVERY",
]
