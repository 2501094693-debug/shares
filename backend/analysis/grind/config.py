"""阴跌 / 横盘筛选：权重与尺度。无硬门槛，全部软评分。"""

from __future__ import annotations

# 回看窗口（交易日）：用来算窗口质量，扫描可更长
DEFAULT_LOOKBACK_DAYS = 60

# K 线尽量多拉，给时长扫描留余量（腾讯日 K 上限约 640）
KLINE_LIMIT = 320

# 展示用走势图
CHART_PAD_BEFORE = 10
CHART_PAD_AFTER = 2
CHART_MAX_BARS = 90
CHART_MA_WARMUP = 20

# 从最近一根向前扫时，单日得分低于此值开始计「中断」
CONSOLIDATION_DAILY_THRESHOLD = 0.38
DECLINE_DAILY_THRESHOLD = 0.38
SCAN_SLACK = 1
SCAN_MAX_DAYS = 120

# 扫描时的累计形态约束（软停，不是入选门槛）
DECLINE_STOP_TOTAL_PCT = 1.5
DECLINE_STOP_RANGE_PCT = 55.0
DECLINE_STOP_PEAK_EXCESS = 0.12
CONSOLIDATION_STOP_RANGE_PCT = 22.0
CONSOLIDATION_STOP_ABS_TOTAL_PCT = 12.0

# 时长分饱和尺度：越大则同样天数得分越低
CONSOLIDATION_DURATION_SCALE = 28.0
DECLINE_DURATION_SCALE = 40.0

# 阴跌 / 横盘各自综合分的内部权重
PATTERN_WEIGHTS: dict[str, float] = {
    "duration": 0.25,
    "quality": 0.60,
    "persistence": 0.15,
}

# 两种形态都明显时的结构加成上限
DUAL_PATTERN_BONUS = 8.0
