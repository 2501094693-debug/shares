"""阴跌→横盘→涨停筛选：权重与阈值。"""

from __future__ import annotations

# 近期涨停窗口（交易日）
DEFAULT_LOOKBACK_DAYS = 15

# K 线尽量多拉（腾讯日 K 上限约 640）
KLINE_LIMIT = 640

# 展示用走势图：与公司详情日 K 一致（约 90 根可视 + 均线预热）
CHART_PAD_BEFORE = 12
CHART_PAD_AFTER = 6
CHART_MAX_BARS = 90
CHART_MA_WARMUP = 20

# 向前扫描时，单日得分低于此值则结束该阶段
CONSOLIDATION_DAILY_THRESHOLD = 0.35
DECLINE_DAILY_THRESHOLD = 0.35

# 时长分饱和尺度：越大则同样天数得分越低
CONSOLIDATION_DURATION_SCALE = 15.0
DECLINE_DURATION_SCALE = 25.0

# 综合得分权重（合计 1.0）
WEIGHTS: dict[str, float] = {
    "decline_duration": 0.20,
    "decline_quality": 0.15,
    "consolidation_duration": 0.20,
    "consolidation_quality": 0.15,
    "breakout": 0.20,
    "structure": 0.10,
}
