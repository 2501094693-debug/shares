"""主营业务画像 HTTP 路由（对外接口）。

    GET /api/stocks/biz-profile    分章节 Markdown 报告（确定性渲染，无模型）

取数与派生在 :mod:`company.analysis.businessoverview.bizprofile.engine`，
排版在 :mod:`company.analysis.businessoverview.bizprofile.render`。
本模块只做参数解析与结果包装。
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Query

from company.analysis.businessoverview.bizprofile.engine import build_profile
from company.analysis.businessoverview.bizprofile.render import render_markdown
from core.api import err, ok

router = APIRouter()

_CODE_RE = re.compile(r"(\d{6})")

#: 固定取最近 2 期：最新期用于结构/集中度展示，第 2 期用于占比迁移。
#: 报告只消费这两期，调大期数不产生任何新内容，故不再作为可调参数。
LATEST_N = 2


def _resolve_code(code: str, company: str) -> str:
    code = str(code or "").strip()
    if code:
        return code
    match = _CODE_RE.search(str(company or ""))
    return match.group(1) if match else ""


def _dimension_view(pack: dict) -> dict:
    """单个维度的结构化视图（供前端原生渲染，不依赖 Markdown 解析）。"""
    segments = pack.get("_latest_segments") or []
    return {
        "key": pack.get("dimension_key") or "",
        "label": pack.get("dimension") or "",
        "report_date": pack.get("report_date") or "",
        "count": len(segments),
        "total_ratio": pack.get("total_ratio"),
        "total_revenue": sum(float(s.get("revenue") or 0.0) for s in segments),
        "overall_margin": pack.get("_overall_margin"),
        "concentration": pack.get("_concentration") or {},
        "segments": [
            {
                "item_name": s.get("item_name") or "",
                "level": s.get("level") or "1",
                "revenue": s.get("revenue"),
                "revenue_ratio": s.get("revenue_ratio"),
                "revenue_yoy": s.get("revenue_yoy"),
                "cost": s.get("cost"),
                "gross_profit": s.get("gross_profit"),
                "gross_profit_ratio": s.get("gross_profit_ratio"),
                "gross_margin": s.get("gross_margin"),
            }
            for s in segments
        ],
        "migration": pack.get("_migration") or [],
    }


@router.get("/api/stocks/biz-profile")
def stocks_biz_profile(
    code: str = Query("", description="股票代码，如 600990"),
    company: str = Query("", description="公司查询串；与 code 二选一"),
    text: str = Query("1", description="1=抓取主营介绍（SSR）"),
    markdown: str = Query("1", description="1=返回 Markdown 全文"),
):
    """主营业务画像：分章节 Markdown 报告。

    全部由确定性规则渲染，**不调用任何模型**；所有数字取自同花顺 F10
    经营分析，或由其派生（派生方式在报告各章节内注明）。

    除 ``markdown`` 全文外，还返回 ``dimensions`` 等结构化字段，
    供前端直接渲染表格与图表，无需解析 Markdown。
    """
    resolved = _resolve_code(code, company)
    if not resolved:
        return err("缺少参数 code", 400)
    try:
        profile = build_profile(
            resolved,
            latest_n=LATEST_N,
            with_text=text == "1",
        )
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)

    primary_key = profile.get("primary") or ""
    primary = (profile.get("dimensions") or {}).get(primary_key) or {}

    body: dict = {
        "code": profile.get("code"),
        "name": profile.get("name"),
        "source": profile.get("source"),
        "source_label": profile.get("source_label"),
        "page": profile.get("page"),
        "cutoff_date": profile.get("cutoff_date"),
        "primary": primary_key,
        "primary_label": profile.get("primary_label"),
        "dim_periods": profile.get("dim_periods"),
        "dim_latest": profile.get("dim_latest"),
        "guardrails": profile.get("guardrails"),
        # 结构化字段（前端原生渲染用）
        "intro": {
            "main_business": primary.get("main_business") or "",
            "product_type": primary.get("product_type") or "",
            "product_name": primary.get("product_name") or "",
            "product_name_list": primary.get("product_name_list") or [],
            "scope": primary.get("scope") or "",
        },
        "dimensions": [
            _dimension_view(pack)
            for pack in (profile.get("dimensions") or {}).values()
        ],
    }
    if markdown == "1":
        body["markdown"] = render_markdown(profile)
    return ok(body)
