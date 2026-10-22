"""风险打分"""
from __future__ import annotations

from .events import RiskEvent
from .taxonomy import RiskLevel

LEVEL_BASE = {"HIGH": 90, "MID": 60, "LOW": 30}

KEYWORD_BONUS = [
    ("问询函", 12),
    ("关注函", 10),
    ("监管函", 10),
    ("立案", 12),
    ("行政处罚", 14),
    ("责令整改", 12),
    ("责令改正", 12),
    ("警示函", 10),
    ("监管警示", 10),
    ("纪律处分", 12),
    ("通报批评", 10),
    ("监管措施", 8),
    ("资金占用", 14),
    ("非经营性资金占用", 16),
    ("对外担保", 10),
    ("冻结", 10),
    ("查封", 10),
    ("平仓", 10),
    ("强制平仓", 12),
    ("减持", 6),
    ("质押", 6),
    ("诉讼", 8),
    ("仲裁", 8),
    ("判决", 6),
    ("补充更正", 6),
    ("更正", 4),
    ("特别处理", 12),
    ("退市风险", 14),
    ("终止上市", 16),
    ("停牌", 6),
    # 资质 / 许可 / 资格
    ("吊销", 16),
    ("撤销", 12),
    ("失效", 10),
    ("到期未续", 10),
    ("未续期", 10),
    ("资质", 8),
    ("许可证", 10),
    ("经营许可", 10),
    ("认证", 6),
    ("准入", 6),
    ("军队采购", 16),
    ("装备采购", 14),
    ("军品", 12),
    ("采购资格", 14),
    ("供应商资格", 12),
    ("投标资格", 12),
    ("暂停资格", 14),
    ("中止资格", 12),
    ("取消资格", 16),
    ("失去资格", 16),
    ("丧失资格", 16),
    ("限制参与", 12),
    ("禁止参与", 14),
    ("不得参与", 10),
    ("暂不参与", 10),
    ("失信", 12),
    ("禁入", 14),
    ("废标", 12),
    ("流标", 10),
    ("围标", 14),
    ("串标", 14),
    ("抽检", 8),
    ("不合格", 10),
    ("召回", 12),
    ("责令停产", 14),
    ("停产整改", 12),
    ("被暂停", 12),
    ("被取消", 14),
    ("违约", 12),
    ("逾期", 10),
    ("债务重组", 10),
    ("评级下调", 10),
]


def score_event(ev: RiskEvent) -> int:
    base = LEVEL_BASE.get(ev.risk_level, 40)
    title = ev.title or ""
    bonus = 0
    for kw, b in KEYWORD_BONUS:
        if kw in title:
            bonus += b
    if ev.query_id in {"A2_REG_KEYWORD", "A4_QUALIFICATION", "F1_ST_DELIST", "F2_SUSPEND", "B3_GUARANTEE_RELATED"}:
        bonus += 4
    score = base + bonus
    if score > 100:
        score = 100
    return score


def score_all(events: list[RiskEvent]) -> list[dict]:
    out = []
    for ev in events:
        s = score_event(ev)
        level: RiskLevel
        if s >= 85:
            level = "HIGH"
        elif s >= 55:
            level = "MID"
        else:
            level = "LOW"
        d = ev.to_dict()
        d["score"] = s
        d["score_level"] = level
        out.append(d)
    out.sort(key=lambda x: (-x["score"], x.get("published_at") or ""))
    return out
