"""同申万三级行业「八看」横截面比对的指标注册表。

一张表声明全部可比指标，排名 / 分位 / 表格 / 雷达全部由它驱动，避免各处硬编码。

字段：
- ``key``       指标唯一键，同时是快照 ``metrics`` 里的取数键；
- ``label``     中文名（表格列头 / 结论文案）；
- ``unit``      ``pct`` 百分比 / ``yi`` 亿元 / ``x`` 倍数 / ``day`` 天 / ``num`` 纯数 / ``text`` 文本；
- ``direction`` ``higher`` 越大越好 / ``lower`` 越小越好 / ``neutral`` 只展示偏离不排名；
- ``view``      所属「看」：strategy/operating/profit/value/cost/quality/risk/outlook/summary；
- ``group``     表格分组用「看」的名称。

排序方向只影响排名，不影响原始数值本身。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Indicator:
    key: str
    label: str
    unit: str
    direction: str
    view: str
    note: str = ""


@dataclass(frozen=True)
class ViewGroup:
    key: str
    no: int
    name: str
    indicators: tuple[Indicator, ...] = field(default_factory=tuple)


# 「看」顺序与中文名，与财务分析 views.VIEW_NAMES 对齐（此处不含具体文案）
_VIEW_META = {
    "strategy": (1, "一看：战略——资源配置"),
    "operating": (2, "二看：经营资产管理与竞争力"),
    "profit": (3, "三看：效益与质量（核心利润）"),
    "value": (4, "四看：价值创造"),
    "cost": (5, "五看：成本决定机制"),
    "quality": (6, "六看：财务状况质量"),
    "risk": (7, "七看：风险"),
    "outlook": (8, "八看：前景"),
    "summary": (0, "综合评分"),
}


INDICATORS: tuple[Indicator, ...] = (
    # 一看 战略
    Indicator("operating_ratio", "经营性资产占比", "pct", "neutral", "strategy"),
    Indicator("investing_ratio", "投资性资产占比", "pct", "neutral", "strategy"),
    Indicator("heavy_asset_ratio", "重资产率", "pct", "neutral", "strategy"),
    Indicator("goodwill_ratio", "商誉占资产", "pct", "lower", "strategy"),
    Indicator("strategy_type", "战略类型", "text", "neutral", "strategy"),
    # 二看 竞争
    Indicator("two_ends_index", "两头吃指数", "x", "higher", "operating"),
    Indicator("inventory_days", "存货周转天数", "day", "lower", "operating"),
    Indicator("receivable_days", "应收周转天数", "day", "lower", "operating"),
    Indicator("fixed_turnover", "固定资产周转", "x", "higher", "operating"),
    Indicator("gross_margin", "毛利率", "pct", "higher", "operating"),
    Indicator("two_gold_ratio", "两金占比", "pct", "lower", "operating"),
    # 三看 效益
    Indicator("core_profit", "核心利润", "yi", "higher", "profit"),
    Indicator("core_margin", "核心利润率", "pct", "higher", "profit"),
    Indicator("deduct_ratio", "扣非占比", "pct", "higher", "profit"),
    Indicator("net_margin", "净利率", "pct", "higher", "profit"),
    # 四看 价值
    Indicator("roe", "ROE", "pct", "higher", "value"),
    Indicator("roa", "ROA", "pct", "higher", "value"),
    Indicator("asset_turnover", "资产周转", "x", "higher", "value"),
    Indicator("equity_multiplier", "权益乘数", "x", "neutral", "value"),
    # 五看 成本
    Indicator("cogs_ratio", "营业成本率", "pct", "lower", "cost"),
    Indicator("sale_exp_ratio", "销售费用率", "pct", "lower", "cost"),
    Indicator("manage_exp_ratio", "管理费用率", "pct", "lower", "cost"),
    Indicator("rd_exp_ratio", "研发费用率", "pct", "neutral", "cost"),
    Indicator("fin_exp_ratio", "财务费用率", "pct", "lower", "cost"),
    Indicator("period_exp_ratio", "期间费用率合计", "pct", "lower", "cost"),
    # 六看 质量
    Indicator("debt_ratio", "资产负债率", "pct", "lower", "quality"),
    Indicator("financial_liab_ratio", "金融性负债占比", "pct", "lower", "quality"),
    Indicator("operating_liab_ratio", "经营性负债占比", "pct", "higher", "quality"),
    Indicator("ocf_core_ratio", "OCF/核心利润", "pct", "higher", "quality"),
    Indicator("ocf_profit_ratio", "OCF/净利润", "pct", "higher", "quality"),
    Indicator("cash_collection_ratio", "销售收现比", "pct", "higher", "quality"),
    Indicator("fcf", "自由现金流", "yi", "higher", "quality"),
    # 七看 风险
    Indicator("risk_hits", "风险命中项数", "num", "lower", "risk"),
    # 八看 前景
    Indicator("revenue_yoy", "营收同比", "pct", "higher", "outlook"),
    Indicator("core_yoy", "核心利润同比", "pct", "higher", "outlook"),
    Indicator("ocf_yoy", "经营现金流同比", "pct", "higher", "outlook"),
    # 综合
    Indicator("score_total", "综合评分", "num", "higher", "summary"),
)

# 只看方向性指标做排名；neutral 只算「高于/低于中位数」
_BY_KEY: dict[str, Indicator] = {ind.key: ind for ind in INDICATORS}


def get_indicator(key: str) -> Indicator | None:
    return _BY_KEY.get(key)


def indicator_keys(view: str = "", *, ranked_only: bool = False) -> list[str]:
    """按「看」取指标 key 列表；``view`` 为空返回全部。"""
    view = (view or "").strip().lower()
    return [
        ind.key
        for ind in INDICATORS
        if (not view or ind.view == view)
        and (not ranked_only or ind.direction != "neutral")
    ]


def view_groups() -> list[ViewGroup]:
    """按一看~八看 + 综合顺序返回分组结构。"""
    order = ["strategy", "operating", "profit", "value", "cost", "quality", "risk", "outlook", "summary"]
    groups: list[ViewGroup] = []
    for view in order:
        no, name = _VIEW_META[view]
        members = tuple(ind for ind in INDICATORS if ind.view == view)
        if members:
            groups.append(ViewGroup(key=view, no=no, name=name, indicators=members))
    return groups


def view_name(view: str) -> str:
    return _VIEW_META.get(view, (0, ""))[1]
