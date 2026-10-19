"""主营构成取数与格式统一（无模型、无二次加工）。

只回答一个问题：**这家公司的主营业务包含哪些部分、各占多少**。
返回的字段全部来自数据源（同花顺 F10 经营分析），仅做**格式统一**：
字段名、字段集、类型、单位（元）、日期（YYYY-MM-DD）、维度键、排序。

明确**不做**的事：不剔除任何分部行（含二级子项、抵销行、小占比业务）、
不合并、不改名、不分级、不打分、不打标、不做交叉校验、
不生成任何描述文字或报告。

分层
----
``interfaces/``  对外接口（HTTP + CLI），集中一处
``core/``        数据源适配器 + 取数编排 + 格式统一（与数据源无关）
``tonghuashun/`` 同花顺接入（唯一数据源）
``bizprofile/``  派生层：分章节 Markdown 报告（确定性渲染，不调模型）
``rules/``       已下线的加工规则（保留知识资产，主链路不引用）

用法
----
>>> from company.analysis.businessoverview import analyze_business_overview
>>> profile = analyze_business_overview("600990")
>>> profile["segments"]

CLI::

    python -m company.analysis.businessoverview 600990
    python -m company.analysis.businessoverview 600990 raw
    python -m company.analysis.businessoverview 600990 periods

    python -m company.analysis.businessoverview.bizprofile 600990   # 报告

HTTP::

    GET /api/stocks/business-overview?code=600990
    GET /api/stocks/business-segments?code=600990
    GET /api/stocks/business-periods?code=600990
    GET /api/stocks/business-sources
    GET /api/stocks/biz-profile?code=600990
"""

from __future__ import annotations

from company.analysis.businessoverview.core.engine import analyze_business_overview
from company.analysis.businessoverview.core.normalize import (
    PACK_FIELDS,
    SEGMENT_FIELDS,
    normalize_pack,
    normalize_segment,
    normalize_segments,
)
from company.analysis.businessoverview.core.source import (
    Source,
    get_source,
    list_sources,
)
from company.analysis.businessoverview.interfaces.api import router

__all__ = [
    "analyze_business_overview",
    "Source",
    "get_source",
    "list_sources",
    "router",
    "PACK_FIELDS",
    "SEGMENT_FIELDS",
    "normalize_pack",
    "normalize_segment",
    "normalize_segments",
]
