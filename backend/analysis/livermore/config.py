"""利弗莫尔规则引擎：ATR 倍数、活跃度、缓存版本。"""

from __future__ import annotations

# 日 K 根数。腾讯个股日 K 上限约 640。
KLINE_LIMIT = 320
ATR_WINDOW = 20
SWING_LEFT = 5

# 1940 年约 6 点 / 3 点 → 用 ATR 缩放
REACTION_ATR = 1.0
CONFIRM_ATR = 0.5
APPROACH_ATR = 0.35
FAIL_ATR = 0.30

# 上升趋势跌破关键点多少 ATR 视为反转
REVERSAL_ATR = 2.0

# 关键点刚穿过后的跟踪窗口
FOLLOW_DAYS = 8
STALL_DAYS = 3
VOLUME_LOOKBACK = 20
BREAKOUT_VOLUME_RATIO = 1.3

# 组内相对强度：前 20% 才算领头股
RS_DAYS = 20
RS_TOP_PCT = 0.20
MIN_L3_PEERS = 3

# 活跃度：近 20 日 ATR% 、日均成交额（元）
LIVE_ATR_PCT = 1.2
LIVE_AMOUNT = 30_000_000.0

# 自然回撤持续多久才把前高当成箱顶关键点
BOX_MIN_DAYS = 8
HIGH_52W_BARS = 250

INDEX_CODE = "SH000001"
INDEX_NAME = "上证指数"
RULESET = "livermore-v1"
CACHE_TAG = "lv1"

DEFAULT_LOOKBACK_DAYS = 60
MIN_BARS = ATR_WINDOW + 5

ACTIONS = ("probe", "pyramid", "hold", "wait", "exit", "cash")
COLUMNS = (
    "uptrend",
    "natural_reaction",
    "secondary_reaction",
    "downtrend",
    "natural_rally",
    "secondary_rally",
    "unclear",
)

COLUMN_LABELS = {
    "uptrend": "上升趋势",
    "natural_reaction": "自然回撤",
    "secondary_reaction": "二次回撤",
    "downtrend": "下降趋势",
    "natural_rally": "自然回升",
    "secondary_rally": "二次回升",
    "unclear": "不明",
}

ACTION_LABELS = {
    "probe": "试探",
    "pyramid": "加码",
    "hold": "持有",
    "wait": "等待",
    "exit": "离场",
    "cash": "空仓",
}

BULL_COLUMNS = {"uptrend", "natural_reaction", "secondary_reaction"}
BEAR_COLUMNS = {"downtrend", "natural_rally", "secondary_rally"}
# 大盘处于上升趋势或其回撤中才允许新开多；下跌趋势里的反弹不当新开仓。
INDEX_ALLOW_COLUMNS = BULL_COLUMNS
