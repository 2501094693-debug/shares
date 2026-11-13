"""全市场最近最低筛选：默认参数与并发。"""

from __future__ import annotations

DEFAULT_ADJUST = "qfq"
DEFAULT_WORKERS = 16
MIN_WORKERS = 1
MAX_WORKERS = 32

# 进度回调节流：每完成 N 只推一次
PROGRESS_EVERY = 20

# 落盘键版本，算法变更后与旧缓存隔离
CACHE_TAG = "rl1"

ALLOWED_ADJUSTS = ("qfq", "hfq", "none")

__all__ = [
    "ALLOWED_ADJUSTS",
    "CACHE_TAG",
    "DEFAULT_ADJUST",
    "DEFAULT_WORKERS",
    "MAX_WORKERS",
    "MIN_WORKERS",
    "PROGRESS_EVERY",
]
