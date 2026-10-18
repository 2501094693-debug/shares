"""八看「全量计算结果」目录：供竞争分析的同行明细矩阵使用。

与 ``registry.py``（精选可比指标，用于排名 / 基准 / 结论）不同，本表追求**穷尽**：
把张新民八看每一看里确定性引擎算出的全部结果都登记进来，逐公司在矩阵里列出。

字段与 ``registry.Indicator`` 一致：``unit`` 为 ``pct/yi/x/day/num/text``，
``direction`` 为 ``higher/lower/neutral``（neutral 只展示不排名）。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Result:
    key: str
    label: str
    unit: str
    direction: str


# 每个「看」的全部计算结果（行顺序即矩阵中的呈现顺序）
FULL_VIEW_RESULTS: dict[str, tuple[Result, ...]] = {
    # 一看：战略——资源配置
    "strategy": (
        Result("operating_assets", "经营性资产", "yi", "neutral"),
        Result("operating_ratio", "经营性资产占比", "pct", "neutral"),
        Result("investing_assets", "投资性资产", "yi", "neutral"),
        Result("investing_ratio", "投资性资产占比", "pct", "neutral"),
        Result("heavy_asset_ratio", "重资产率", "pct", "neutral"),
        Result("goodwill_ratio", "商誉占资产", "pct", "lower"),
        Result("strategy_type", "战略类型", "text", "neutral"),
    ),
    # 二看：经营资产管理与竞争力
    "operating": (
        Result("two_ends_index", "两头吃指数", "x", "higher"),
        Result("inventory_days", "存货周转天数", "day", "lower"),
        Result("receivable_days", "应收周转天数", "day", "lower"),
        Result("fixed_turnover", "固定资产周转", "x", "higher"),
        Result("two_gold", "两金合计", "yi", "neutral"),
        Result("two_gold_ratio", "两金占比", "pct", "lower"),
        Result("gross_margin", "毛利率", "pct", "higher"),
    ),
    # 三看：效益与质量（核心利润）
    "profit": (
        Result("core_profit", "核心利润", "yi", "higher"),
        Result("core_margin", "核心利润率", "pct", "higher"),
        Result("non_core_profit", "非核心损益", "yi", "neutral"),
        Result("deduct_ratio", "扣非占比", "pct", "higher"),
        Result("net_margin", "净利率", "pct", "higher"),
    ),
    # 四看：价值创造
    "value": (
        Result("roe", "ROE", "pct", "higher"),
        Result("roa", "ROA", "pct", "higher"),
        Result("asset_turnover", "资产周转", "x", "higher"),
        Result("equity_multiplier", "权益乘数", "x", "neutral"),
    ),
    # 五看：成本决定机制
    "cost": (
        Result("cogs_ratio", "营业成本率", "pct", "lower"),
        Result("sale_exp_ratio", "销售费用率", "pct", "lower"),
        Result("manage_exp_ratio", "管理费用率", "pct", "lower"),
        Result("rd_exp_ratio", "研发费用率", "pct", "neutral"),
        Result("fin_exp_ratio", "财务费用率", "pct", "lower"),
        Result("period_exp_ratio", "期间费用率合计", "pct", "lower"),
    ),
    # 六看：财务状况质量
    "quality": (
        Result("financial_liabilities", "金融性负债", "yi", "neutral"),
        Result("financial_liab_ratio", "金融性负债占比", "pct", "lower"),
        Result("operating_liabilities", "经营性负债", "yi", "neutral"),
        Result("operating_liab_ratio", "经营性负债占比", "pct", "higher"),
        Result("debt_ratio", "资产负债率", "pct", "lower"),
        Result("fcf", "自由现金流", "yi", "higher"),
        Result("ocf_core_ratio", "OCF/核心利润", "pct", "higher"),
        Result("ocf_profit_ratio", "OCF/净利润", "pct", "higher"),
        Result("cash_collection_ratio", "销售收现比", "pct", "higher"),
        Result("cashflow_mode", "现金流模式", "text", "neutral"),
    ),
    # 七看：风险（命中项数 + 触发明细）
    "risk": (
        Result("risk_hits", "风险命中项数", "num", "lower"),
        Result("risk_flags", "风险警示", "text", "neutral"),
    ),
    # 八看：前景
    "outlook": (
        Result("revenue_yoy", "营收同比", "pct", "higher"),
        Result("core_yoy", "核心利润同比", "pct", "higher"),
        Result("ocf_yoy", "经营现金流同比", "pct", "higher"),
        Result("operating_asset_yoy", "经营性资产同比", "pct", "higher"),
        Result("investing_asset_yoy", "投资性资产同比", "pct", "higher"),
    ),
    # 综合评分
    "summary": (
        Result("score_total", "综合评分", "num", "higher"),
    ),
}


def full_view_indicators(view: str) -> list[dict[str, str]]:
    """返回某一看的全量结果定义（key/label/unit/direction），供前端矩阵表头与行使用。"""
    return [
        {"key": r.key, "label": r.label, "unit": r.unit, "direction": r.direction}
        for r in FULL_VIEW_RESULTS.get((view or "").strip().lower(), ())
    ]
