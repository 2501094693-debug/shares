"""MACD 稳定区间筛选：默认参数与并发。"""

from __future__ import annotations

from company.analysis.line.evaluate.core import DEFAULT_BAND
from company.analysis.line.evaluate.service import (
    DEFAULT_INDEX,
    DEFAULT_LOOKBACK_DAYS,
)
from company.analysis.line.MACD.core import (
    DEFAULT_FAST,
    DEFAULT_SIGNAL,
    DEFAULT_SLOW,
)

# 即将金叉：相对缺口阈值 (DEA−DIF)/(|DEA|+ε) ≤ θ
DEFAULT_NEAR_RATIO = 0.10
# 综合分权重：前低均分 / 股指反向日占比分
DEFAULT_W_PRIOR = 0.70
DEFAULT_W_DIV = 0.30

DEFAULT_FACTOR = "close"
DEFAULT_ADJUST = "qfq"
DEFAULT_WORKERS = 16
MIN_WORKERS = 1
MAX_WORKERS = 32

PROGRESS_EVERY = 20

# 落盘键版本，算法变更后与旧缓存隔离
CACHE_TAG = "m1"

ALLOWED_BANDS = (0.05, 0.09, 0.12)
ALLOWED_FACTORS = ("open", "high", "low", "close", "all")
ALLOWED_INDEXES = ("000001", "399001", "000300")
ALLOWED_ADJUSTS = ("qfq", "hfq", "none")

__all__ = [
    "ALLOWED_ADJUSTS",
    "ALLOWED_BANDS",
    "ALLOWED_FACTORS",
    "ALLOWED_INDEXES",
    "CACHE_TAG",
    "DEFAULT_ADJUST",
    "DEFAULT_BAND",
    "DEFAULT_FACTOR",
    "DEFAULT_FAST",
    "DEFAULT_INDEX",
    "DEFAULT_LOOKBACK_DAYS",
    "DEFAULT_NEAR_RATIO",
    "DEFAULT_SIGNAL",
    "DEFAULT_SLOW",
    "DEFAULT_W_DIV",
    "DEFAULT_W_PRIOR",
    "DEFAULT_WORKERS",
    "MAX_WORKERS",
    "MIN_WORKERS",
    "PROGRESS_EVERY",
]
