"""主营业务数据 HTTP 路由（对外接口）。

    GET /api/stocks/business-overview    主营数据（取数 + 格式统一）
    GET /api/stocks/business-segments    主营构成原始结构
    GET /api/stocks/business-periods     可用报告期列表
    GET /api/stocks/business-sources     已接入数据源清单

取数全部经 :mod:`core.source` 适配器，格式统一在 :mod:`core.normalize`。
**不做任何二次加工**：不剔除分部行、不合并小业务、不分级、不打标、
不做交叉校验、不生成描述文字。
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Query

from company.analysis.businessoverview.core.engine import analyze_business_overview
from company.analysis.businessoverview.core.source import get_source, list_sources
from core.api import err, ok

router = APIRouter()

_CODE_RE = re.compile(r"(\d{6})")


def _resolve_code(code: str, company: str) -> str:
    code = str(code or "").strip()
    if code:
        return code
    match = _CODE_RE.search(str(company or ""))
    return match.group(1) if match else ""


@router.get("/api/stocks/business-overview")
def stocks_business_overview(
    code: str = Query("", description="股票代码，如 600990"),
    company: str = Query("", description="公司查询串；与 code 二选一"),
    latest_n: int = Query(2, ge=1, le=6, description="取最近 N 个报告期（默认 2）"),
    dimension: str = Query("", description="拆分维度：1=按产品 2=按行业 3=按地区；留空自动"),
    source: str = Query("", description="数据源：tonghuashun(默认，唯一)"),
    financial: str = Query("1", description="1=附带八看年报经营情况"),
):
    """主营业务数据（取数 + 格式统一，不做二次加工）。

    统一字段契约见 ``core.normalize.PACK_FIELDS``。
    数据源为同花顺 F10 经营分析。
    """
    code = _resolve_code(code, company)
    if not code:
        return err("缺少参数 code", 400)
    try:
        return ok(
            analyze_business_overview(
                code,
                latest_n=latest_n,
                dimension=dimension,
                with_financial=financial == "1",
                source=source,
            )
        )
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/stocks/business-segments")
def stocks_business_segments(
    code: str = Query("", description="股票代码，如 600990"),
    latest_n: int = Query(1, ge=1, le=8, description="取最近 N 个报告期"),
    dimension: str = Query("", description="1=按产品 2=按行业 3=按地区；留空自动"),
    source: str = Query("tonghuashun", description="数据源：tonghuashun(默认，唯一)"),
):
    """仅取主营构成原始结构（接入层直出，未做格式统一）。"""
    code = _resolve_code(code, "")
    if not code:
        return err("缺少参数 code", 400)
    try:
        return ok(get_source(source).segments(code, latest_n=latest_n, dimension=dimension))
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/stocks/business-periods")
def stocks_business_periods(
    code: str = Query("", description="股票代码，如 600990"),
    source: str = Query("tonghuashun", description="数据源：tonghuashun(默认，唯一)"),
):
    """可用报告期列表（降序）。"""
    code = _resolve_code(code, "")
    if not code:
        return err("缺少参数 code", 400)
    try:
        src = get_source(source)
        dates = src.periods(code)
        return ok({"code": code, "source": src.key, "count": len(dates), "periods": dates})
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/stocks/business-sources")
def stocks_business_sources():
    """已接入的数据源清单（自描述，便于前端渲染切换器）。"""
    return ok(
        [
            {
                "key": s.key,
                "label": s.label,
                "api": s.api,
                "page": s.page("{code}"),
                "dimensions": s.dim_labels,
                "dim_priority": list(s.dim_priority),
            }
            for s in list_sources()
        ]
    )
