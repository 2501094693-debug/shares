"""标题 → subcategory 关键词规则。"""

from __future__ import annotations

SUBCATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "inquiry",
        ("问询函", "关注函", "监管函", "警示函", "监管工作函"),
    ),
    (
        "penalty",
        (
            "行政处罚",
            "市场禁入",
            "处罚决定",
            "纪律处分",
            "通报批评",
            "公开谴责",
            "监管措施",
            "责令改正",
            "立案告知",
            "立案调查",
            "立案",
        ),
    ),
    (
        "periodic_report",
        ("年度报告", "年报", "半年度报告", "中报", "一季报", "三季报", "季度报告"),
    ),
    (
        "buyback",
        ("回购", "股份回购"),
    ),
    (
        "equity_change",
        ("增持", "减持", "权益变动", "持股变动", "举牌"),
    ),
    (
        "financing",
        ("定增", "配股", "可转债", "再融资", "发行股份"),
    ),
    (
        "m_and_a",
        ("收购", "重组", "并购", "重大资产"),
    ),
    (
        "dividend",
        ("分红", "派息", "利润分配", "权益分派"),
    ),
    (
        "risk_warning",
        ("风险提示", "退市风险", "其他风险警示", "*ST", "ST"),
    ),
)


def infer_subcategory(title: str, *, fallback: str = "general") -> str:
    text = title or ""
    for sub, keys in SUBCATEGORY_RULES:
        if any(k in text for k in keys):
            return sub
    return fallback
