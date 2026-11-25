"""MACD 稳定区间筛选：默认参数与并发。"""

from __future__ import annotations

from company.analysis.line.evaluate.core import DEFAULT_BAND
from company.analysis.line.evaluate.service import DEFAULT_INDEX
from company.analysis.line.MACD.core import (
    DEFAULT_FAST,
    DEFAULT_SIGNAL,
    DEFAULT_SLOW,
)

# 回溯自然日（稳定区间 / 前低打分）；金叉本身只看截止日最近两根 K
DEFAULT_LOOKBACK_DAYS = 240

# 即将金叉相对缺口阈值；与速度外推任一命中即可
DEFAULT_NEAR_RATIO = 0.10
# 综合分权重：前低均分 / 股指反向日占比分
DEFAULT_W_PRIOR = 0.70
DEFAULT_W_DIV = 0.30

# 信号类别：全部 / 水下类（水下金叉+即将水下金叉）/ 水上类（水上金叉+即将水上金叉）
CROSS_TYPE_ALL = "all"
CROSS_TYPE_UNDER = "under"
CROSS_TYPE_OVER = "over"
ALLOWED_CROSS_TYPES = (CROSS_TYPE_ALL, CROSS_TYPE_UNDER, CROSS_TYPE_OVER)
DEFAULT_CROSS_TYPE = CROSS_TYPE_ALL

DEFAULT_FACTOR = "close"
DEFAULT_ADJUST = "qfq"
DEFAULT_WORKERS = 16
MIN_WORKERS = 1
MAX_WORKERS = 32

PROGRESS_EVERY = 20

# 区间回测：最多覆盖的交易日数（逐日全市场扫描很重；约覆盖默认「最近两个月」）
MAX_RANGE_DAYS = 50
# 区间回测落盘键版本
RANGE_CACHE_TAG = "r3"

# 落盘键版本，算法变更后与旧缓存隔离
CACHE_TAG = "m3"

ALLOWED_BANDS = (0.05, 0.09, 0.12)
ALLOWED_FACTORS = ("open", "high", "low", "close", "all")
ALLOWED_INDEXES = ("000001", "399001", "000300")
ALLOWED_ADJUSTS = ("qfq", "hfq", "none")

__all__ = [
    "ALLOWED_ADJUSTS",
    "ALLOWED_BANDS",
    "ALLOWED_CROSS_TYPES",
    "ALLOWED_FACTORS",
    "ALLOWED_INDEXES",
    "CACHE_TAG",
    "CROSS_TYPE_ALL",
    "CROSS_TYPE_OVER",
    "CROSS_TYPE_UNDER",
    "DEFAULT_ADJUST",
    "DEFAULT_BAND",
    "DEFAULT_CROSS_TYPE",
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
    "MAX_RANGE_DAYS",
    "MAX_WORKERS",
    "MIN_WORKERS",
    "PROGRESS_EVERY",
    "RANGE_CACHE_TAG",
]
