"""deal 子包的共享常量。

集中管理窗口重建 / 逐笔撮合中用到的数值阈值、买卖方向集合与集合竞价时段，
供 ``constants`` / ``util`` / ``ingest`` / ``cost`` 等模块复用。
"""

from __future__ import annotations

# 一手 = 100 股（仅用于金额 ↔ 手数换算；成交手数本身一律整手）
SHARES_PER_LOT = 100.0

# 资金动向收录门槛：单笔成交额 >= 该值即为「大单」
DEFAULT_TRADE_THRESHOLD = 300_000.0

# 分时快照缺笔数时，按笔均手数反推
DEFAULT_AVG_LOTS_PER_TICK = 3.0

# 单笔最小规模：默认 0 手。禁止小数手，只允许 0 / 1 / 2 … 整手。
DEFAULT_MIN_LOTS = 0.0
TRADE_MIN_LOTS = 0.0

# 价格比较容差（判断「同价」时使用）
PRICE_EPS = 0.005

# 内部浮点容差
EPS = 1e-9

# ---------------------------------------------------------------------------
# 买卖方向 / 集合竞价相关集合与时段（供 ingest 使用）
# ---------------------------------------------------------------------------

# 视为「买」的方向集合（side 或 side_label 归一后比对）
BUY_SIDES = {"1", "b", "buy", "买", "买盘", "b1", "2"}

# 集合竞价方向集合（累计虚拟撮合快照）
AUCTION_SIDES = {"4", "auction"}

# 集合竞价虚拟撮合快照时段（应剔除，避免累计量重复计入）
AUCTION_WINDOWS = (("09:15:00", "09:25:00"), ("14:57:00", "15:00:00"))

# 集合竞价**真实成交**落点：开盘撮合在 09:25（个别源会散落在随后几秒），收盘在 15:00
CALL_AUCTION_MATCH = (("09:25:00", "09:26:00"), ("15:00:00", "15:01:00"))

# 开盘撮合之后、连续竞价之前：不应有新成交
PRE_CONTINUOUS_GAP = (("09:26:00", "09:30:00"),)

# ---------------------------------------------------------------------------
# 订单角色
# ---------------------------------------------------------------------------

ROLE_ACTIVE = "active"
ROLE_PASSIVE = "passive"
ROLE_OTHER = "other"


__all__ = [
    "AUCTION_SIDES",
    "AUCTION_WINDOWS",
    "BUY_SIDES",
    "CALL_AUCTION_MATCH",
    "DEFAULT_AVG_LOTS_PER_TICK",
    "DEFAULT_MIN_LOTS",
    "DEFAULT_TRADE_THRESHOLD",
    "EPS",
    "PRE_CONTINUOUS_GAP",
    "PRICE_EPS",
    "ROLE_ACTIVE",
    "ROLE_OTHER",
    "ROLE_PASSIVE",
    "SHARES_PER_LOT",
    "TRADE_MIN_LOTS",
]
