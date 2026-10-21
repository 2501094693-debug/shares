"""风险排查七维与查询清单（仅使用 fetch_announcements）"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RiskLevel = Literal["HIGH", "MID", "LOW"]
RiskType = Literal[
    "REGULATORY",
    "GOVERNANCE",
    "SHAREHOLDER",
    "FINANCING",
    "DISCLOSURE",
    "LITIGATION",
    "CONTINUITY",
    "BUSINESS",
    "COMMUNICATION",
    "OTHER",
]


@dataclass(slots=True)
class RiskQuery:
    """只用 fetch_announcements 的查询定义"""

    qid: str
    title: str
    risk_type: RiskType
    level: RiskLevel
    desc: str
    tab: str = "fulltext"
    category: list[str] | None = None
    keyword: str = ""
    days: int = 365
    enabled: bool = True


@dataclass(slots=True)
class RiskDimension:
    """前端按维展示：检索方式 + 按子查询分组的检索结果。"""

    key: str
    no: int
    name: str
    query_ids: tuple[str, ...]


# 风险查询清单（仅调用 fetch_announcements）
RISK_QUERIES: list[RiskQuery] = [
    # A. 监管与合规
    RiskQuery(
        qid="A1_SUPERVISE",
        title="持续督导（监管关注）",
        risk_type="REGULATORY",
        level="HIGH",
        desc="巨潮「持续督导」页签，覆盖交易所/监管跟进",
        tab="supervise",
        days=365,
    ),
    RiskQuery(
        qid="A2_REG_KEYWORD",
        title="问询函/关注函/立案/处罚",
        risk_type="REGULATORY",
        level="HIGH",
        desc="标题中出现监管问询、立案、稽查、行政处罚等",
        keyword="问询函|关注函|监管函|立案|立案调查|调查|稽查|行政处罚|责令整改|监管措施|监管谈话|下发问询",
        days=365,
    ),
    RiskQuery(
        qid="A3_LITIGATION",
        title="诉讼、仲裁、执行",
        risk_type="LITIGATION",
        level="HIGH",
        desc="或有负债、赔付风险",
        keyword="诉讼|仲裁|起诉|被诉|民事诉讼|行政诉讼|判决|裁定|强制执行|执行通知|财产保全",
        days=365,
    ),
    RiskQuery(
        qid="A4_QUALIFICATION",
        title="资质/采购资格（军队采购等）",
        risk_type="REGULATORY",
        level="HIGH",
        desc="经营资质类负面，常在日常经营中披露，难以归入专属 category",
        keyword="军队采购|装备采购|军品|采购资格|供应商资格|暂停资格|中止资格|取消资格|被暂停|被取消",
        days=365,
    ),
    # B. 治理与内控
    RiskQuery(
        qid="B1_THREE_MEETINGS",
        title="董事会/股东大会/监事会",
        risk_type="GOVERNANCE",
        level="MID",
        desc="担保、关联交易、重大合同、异议等议案",
        category=["董事会", "股东大会", "监事会"],
        days=180,
    ),
    RiskQuery(
        qid="B2_CORP_GOV",
        title="公司治理",
        risk_type="GOVERNANCE",
        level="MID",
        desc="治理制度、内控相关变更",
        category=["公司治理"],
        days=365,
    ),
    RiskQuery(
        qid="B3_GUARANTEE_RELATED",
        title="担保、关联交易、资金占用",
        risk_type="GOVERNANCE",
        level="HIGH",
        desc="标题兜底（有些议案未能被 category 精准覆盖）",
        keyword="关联交易|对外担保|对外提供担保|连带责任|担保额度|资金占用|非经营性资金占用|财务资助|委托贷款",
        days=365,
    ),
    # C. 股本结构与控制权
    RiskQuery(
        qid="C1_EQUITY",
        title="股权变动/解禁/股权激励",
        risk_type="SHAREHOLDER",
        level="MID",
        desc="股权转让、解禁安排、激励等",
        category=["股权变动", "解禁", "股权激励"],
        days=365,
    ),
    RiskQuery(
        qid="C2_REDUCE_PLEDGE",
        title="减持、质押、冻结、控制权",
        risk_type="SHAREHOLDER",
        level="HIGH",
        desc="大股东减持、质押、冻结、平仓、控制权变更",
        keyword="减持|减持计划|减持实施|股东减持|质押|质押解除|股票质押|冻结|轮候冻结|查封|轮候查封|平仓|强制平仓|控制权变更|权益变动",
        days=365,
    ),
    # D. 资本运作与债务
    RiskQuery(
        qid="D1_FINANCING",
        title="增发/配股/可转债/其他融资/首发",
        risk_type="FINANCING",
        level="MID",
        desc="再融资、股权稀释、杠杆变化",
        category=["增发", "配股", "可转债", "其他融资", "首发"],
        days=365,
    ),
    RiskQuery(
        qid="D2_DEBT",
        title="债务、违约、展期、兑付、信用",
        risk_type="FINANCING",
        level="HIGH",
        desc="偿债压力相关线索",
        keyword="违约|逾期|到期未偿|债务|债券违约|展期|兑付|兑付失败|债务重组|信用评级|评级下调",
        days=365,
    ),
    # E. 披露质量
    RiskQuery(
        qid="E1_AMEND",
        title="补充更正",
        risk_type="DISCLOSURE",
        level="MID",
        desc="前期公告更正，频繁出现需警惕",
        category=["补充更正"],
        days=730,
    ),
    RiskQuery(
        qid="E2_INTERMEDIARY",
        title="中介报告",
        risk_type="DISCLOSURE",
        level="MID",
        desc="审计、评估、法律意见等中介报告",
        category=["中介报告"],
        days=365,
    ),
    RiskQuery(
        qid="E3_ERRATA",
        title="更正、勘误、致歉",
        risk_type="DISCLOSURE",
        level="MID",
        desc="披露差错类",
        keyword="更正|勘误|更正公告|致歉|情况说明|补充说明",
        days=365,
    ),
    # F. 存续性
    RiskQuery(
        qid="F1_ST_DELIST",
        title="特别处理/退市整理",
        risk_type="CONTINUITY",
        level="HIGH",
        desc="ST、退市风险警示、退市整理期",
        category=["特别处理", "退市整理"],
        days=730,
    ),
    RiskQuery(
        qid="F2_SUSPEND",
        title="停牌、复牌、终止上市、风险警示",
        risk_type="CONTINUITY",
        level="HIGH",
        desc="交易状态异常、退市进程",
        keyword="停牌|复牌|临时停牌|终止上市|上市地位变更|风险警示|退市风险警示",
        days=730,
    ),
    # G. 经营与沟通
    RiskQuery(
        qid="G1_OPERATION",
        title="日常经营/权益分派",
        risk_type="BUSINESS",
        level="LOW",
        desc="重大合同、中标、业绩等（部分为正面也可能转为负面）",
        category=["日常经营", "权益分派"],
        days=365,
    ),
    RiskQuery(
        qid="G2_SURVEYS",
        title="投资者关系/调研",
        risk_type="COMMUNICATION",
        level="LOW",
        desc="管理层表述变化、市场关注点线索",
        tab="relation",
        days=180,
    ),
]


# 七个维度：检索方式由 query_ids 形式化生成；结果按子查询分组
RISK_DIMENSIONS: list[RiskDimension] = [
    RiskDimension(
        key="regulatory",
        no=1,
        name="监管与合规",
        query_ids=("A1_SUPERVISE", "A2_REG_KEYWORD", "A3_LITIGATION", "A4_QUALIFICATION"),
    ),
    RiskDimension(
        key="governance",
        no=2,
        name="治理与内控",
        query_ids=("B1_THREE_MEETINGS", "B2_CORP_GOV", "B3_GUARANTEE_RELATED"),
    ),
    RiskDimension(
        key="shareholder",
        no=3,
        name="股本结构与控制权",
        query_ids=("C1_EQUITY", "C2_REDUCE_PLEDGE"),
    ),
    RiskDimension(
        key="financing",
        no=4,
        name="资本运作与债务",
        query_ids=("D1_FINANCING", "D2_DEBT"),
    ),
    RiskDimension(
        key="disclosure",
        no=5,
        name="披露质量",
        query_ids=("E1_AMEND", "E2_INTERMEDIARY", "E3_ERRATA"),
    ),
    RiskDimension(
        key="continuity",
        no=6,
        name="存续性",
        query_ids=("F1_ST_DELIST", "F2_SUSPEND"),
    ),
    RiskDimension(
        key="business",
        no=7,
        name="经营与沟通",
        query_ids=("G1_OPERATION", "G2_SURVEYS"),
    ),
]


def get_enabled_queries() -> list[RiskQuery]:
    return [q for q in RISK_QUERIES if q.enabled]


def get_query_map() -> dict[str, RiskQuery]:
    return {q.qid: q for q in RISK_QUERIES}


def get_dimensions() -> list[RiskDimension]:
    return list(RISK_DIMENSIONS)
