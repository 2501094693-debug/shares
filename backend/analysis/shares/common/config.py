"""日线多日条件筛选：窗口与可选字段说明。"""

from __future__ import annotations

# 约一个交易月；多拉一点给停牌对齐留余量
DEFAULT_LOOKBACK_DAYS = 22
MAX_LOOKBACK_DAYS = 30
KLINE_LIMIT = 48

# 单日条件可填的数值区间字段（单位见 FIELD_META）
RANGE_FIELDS: tuple[str, ...] = (
    "pct_chg",  # 涨跌幅 %
    "max_gain",  # 最大涨幅 %：(最高-昨收)/昨收×100
    "max_drop",  # 最大跌幅 %：(最低-昨收)/昨收×100，多为负
    "body_pct",  # 实体幅度 %：(收-开)/开 ×100，可负
    "body_ratio",  # 实体占全日振幅比例 0–1
    "lower_ratio",  # 下影占比 lower/(高-低) 0–1
    "upper_ratio",  # 上影占比 upper/(高-低) 0–1
    "vol_ratio",  # 量比：当日量 / 前5日均量（不含当日）
    "vol_chg",  # 量增幅 %：(当日量/昨量 − 1)×100
)

FIELD_META: dict[str, dict[str, str]] = {
    "pct_chg": {"label": "涨跌幅", "unit": "%", "hint": "相对昨收"},
    "max_gain": {"label": "最大涨幅", "unit": "%", "hint": "(最高-昨收)/昨收×100"},
    "max_drop": {"label": "最大跌幅", "unit": "%", "hint": "(最低-昨收)/昨收×100，多为负"},
    "body_pct": {"label": "实体幅度", "unit": "%", "hint": "(收盘-开盘)/开盘×100，阳正阴负"},
    "body_ratio": {"label": "实体占比", "unit": "比例", "hint": "实体/(最高-最低)，0–1"},
    "lower_ratio": {"label": "下影占比", "unit": "比例", "hint": "下影/(最高-最低)，0–1"},
    "upper_ratio": {"label": "上影占比", "unit": "比例", "hint": "上影/(最高-最低)，0–1"},
    "vol_ratio": {"label": "量比", "unit": "倍", "hint": "当日量/前5日均量（不含当日）"},
    "vol_chg": {"label": "量增幅", "unit": "%", "hint": "(当日量/昨量−1)×100"},
}

# 跨日对比可用字段 = 区间字段 + 派生绝对值 / 波幅
COMPARE_FIELDS: tuple[str, ...] = RANGE_FIELDS + (
    "body_abs_pct",  # |实体幅度| %
    "abs_pct_chg",  # |涨跌幅| %
    "range_pct",  # 日内波幅 %：max_gain − max_drop
)

COMPARE_FIELD_META: dict[str, dict[str, str]] = {
    **FIELD_META,
    "body_abs_pct": {"label": "|实体|", "unit": "%", "hint": "abs(body_pct)"},
    "abs_pct_chg": {"label": "|涨跌幅|", "unit": "%", "hint": "abs(pct_chg)"},
    "range_pct": {"label": "日内波幅", "unit": "%", "hint": "max_gain − max_drop"},
}

COMPARE_OPS: tuple[str, ...] = ("lt", "le", "gt", "ge", "eq")
COMPARE_TRENDS: tuple[str, ...] = ("down", "up", "flat")
