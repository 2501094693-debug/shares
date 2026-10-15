"""张新民「八看」财报解读 HTTP 路由。"""

from __future__ import annotations

import re

from fastapi import APIRouter, Query

from company.analysis.financialreport.engine import analyze
from company.analysis.financialreport.views import VIEW_NAMES
from core.api import err, ok

router = APIRouter()

_CODE_RE = re.compile(r"(\d{6})")


def _resolve_code(code: str, company: str) -> str:
    """``code`` 优先；否则从 ``company``（如「三星电气 601567」）里抽取 6 位代码。"""
    code = str(code or "").strip()
    if code:
        return code
    match = _CODE_RE.search(str(company or ""))
    return match.group(1) if match else ""


@router.get("/api/stocks/financial-views")
def stocks_financial_views(
    code: str = Query("", description="股票代码，如 601567"),
    company: str = Query("", description="公司查询串（如「三星电气 601567」）；与 code 二选一"),
    report_type: str = Query(
        "annual",
        description="报告口径：annual 年报 | semi 半年报 | q1 一季报 | q3 三季报（也接受 年报/半年报/一季报/三季报）",
    ),
    view: str = Query("", description="只看某一看：strategy|operating|profit|value|cost|quality|risk|outlook|summary；留空返回全部"),
    name: str = Query("", description="公司简称，可选，仅用于回显"),
    limit: int = Query(60, ge=1, le=60, description="拉取的定期报告期数上限"),
    refresh: str = Query("0", description="1=强制刷新（绕过一小时缓存）"),
):
    """张新民「八看」财务分析：八看方法 + 汇总诊断，支持选择年报/半年报/一季报/三季报口径。"""
    code = _resolve_code(code, company)
    if not code:
        return err("缺少参数 code", 400)
    display_name = name.strip() or "".join(str(company or "").replace(code, "").split())
    try:
        data = analyze(
            code,
            report_type=report_type.strip() or "annual",
            name=display_name,
            limit=limit,
            force=refresh == "1",
            view=view.strip(),
        )
        return ok(data)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/stocks/financial-views/meta")
def stocks_financial_views_meta():
    """八看视图目录：key 与中文名称，供前端渲染导航。"""
    return ok([{"key": key, "name": name} for key, name in VIEW_NAMES.items()])
