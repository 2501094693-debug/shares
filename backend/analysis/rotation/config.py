"""三级轮动日历：窗口和软评分权重。"""

from __future__ import annotations

LOOKBACK_1M = 20
LOOKBACK_3M = 60
LOOKBACK_6M = 120
LOOKBACK_1Y = 245
LOOKBACK_2Y = 490
DEFAULT_LOOKBACK_DAYS = LOOKBACK_1Y
MIN_LOOKBACK_DAYS = LOOKBACK_1M
MAX_LOOKBACK_DAYS = LOOKBACK_2Y

# 成分股太少的三级不进宇宙
MIN_STOCKS = 3

# 软评分大于这条才记入榜单；三项等权：涨幅强度、上涨占比、进攻扩散
SCORE_NAMED = 60.0
W_CHANGE = 1.0 / 3.0
W_BREADTH = 1.0 / 3.0
W_LIMIT = 1.0 / 3.0

# 涨幅强度：当天加权涨幅 / 近 N 日（不含当天）样本标准差
SIGMA_DAYS = 20
SIGMA_MIN_DAYS = 10
SIGMA_FLOOR = 0.3

# 三级体量：成分股市值中位数（亿元）
CAP_WEIGHT_YI = 500.0
CAP_MID_YI = 100.0

# 进攻扩散：按个股市值认强势（百分比）
STRONG_WEIGHT_PCT = 2.0
STRONG_MID_PCT = 4.0
STRONG_THEME_PCT = 7.0

# 待涨标签：近5日转强 / 资金先行的参考线
WATCH_CHANGE_PCT = 2.0

# 回填缺快照的交易日：覆盖最长两年窗口
KLINE_LIMIT = 500
KLINE_WORKERS = 16

# 落盘键版本，算法变更后与旧缓存隔离
CACHE_TAG = "s6"
