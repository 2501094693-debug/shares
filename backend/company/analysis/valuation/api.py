"""估值分析 HTTP 路由。

路由：
- GET /api/stocks/valuation          完整估值报告（DCF + 相对估值 + 安全边际）
- GET /api/stocks/valuation/dcf      仅 DCF 内在价值
- GET /api/stocks/valuation/relative 仅相对估值（历史分位 + 同业）
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Query

from company.analysis.valuation.engine import run_valuation
from core.api import err, ok

router = APIRouter()

_CODE_RE = re.compile(r"(\d{6})")


def _resolve_code(code: str, company: str) -> str:
    code = str(code or "").strip()
    if code:
        return code
    match = _CODE_RE.search(str(company or ""))
    return match.group(1) if match else ""


@router.get("/api/stocks/valuation")
def stocks_valuation(
    code: str = Query("", description="股票代码，如 600519"),
    company: str = Query("", description="公司查询串（含 6 位代码即可）；与 code 二选一"),
    name: str = Query("", description="公司简称，可选，仅用于回显"),
    report_type: str = Query(
        "annual",
        description="财报口径：annual 年报 | semi 半年报 | q1 一季报 | q3 三季报",
    ),
    force: str = Query("0", description="1=绕过缓存强制刷新"),
    peer_limit: int = Query(6, ge=0, le=20, description="同业公司上限（逐只取最新倍数）"),
    wacc: float | None = Query(None, ge=0.0, le=1.0, description="折现率，如 0.09 表示 9%"),
    terminal_growth: float | None = Query(
        None, ge=0.0, le=1.0, description="永续增长率，如 0.025 表示 2.5%"
    ),
    projection_years: int | None = Query(
        None, ge=1, le=10, description="DCF 显性预测期年数，缺省 5"
    ),
    first_stage_growth: float | None = Query(
        None, ge=-1.0, le=1.0, description="显性期年复合增长率，缺省由营收 CAGR 推导"
    ),
    safety_discount: float = Query(
        0.0, ge=0.0, le=1.0, description="对内在价值的额外安全发令，如 0.1 表示打九成"
    ),
):
    """完整估值分析：DCF 内在价值 + 相对估值（历史分位/同业） + 安全边际。"""
    resolved = _resolve_code(code, company)
    if not resolved:
        return err("缺少有效的 6 位股票代码", 400)
    try:
        return run_valuation(
            resolved,
            name or company,
            report_type=report_type.strip() or "annual",
            force=force == "1",
            peer_limit=peer_limit,
            wacc=wacc,
            terminal_growth=terminal_growth,
            projection_years=projection_years,
            first_stage_growth=first_stage_growth,
            safety_discount=safety_discount,
        )
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/stocks/valuation/dcf")
def stocks_valuation_dcf(
    code: str = Query("", description="股票代码，如 600519"),
    company: str = Query("", description="公司查询串（含 6 位代码即可）；与 code 二选一"),
    report_type: str = Query("annual", description="财报口径：annual 年报 | semi 半年报 | q1 一季报 | q3 三季报"),
    force: str = Query("0", description="1=绕过缓存强制刷新"),
    wacc: float | None = Query(None, ge=0.0, le=1.0, description="折现率"),
    terminal_growth: float | None = Query(None, ge=0.0, le=1.0, description="永续增长率"),
    projection_years: int | None = Query(None, ge=1, le=10, description="预测期年数"),
    first_stage_growth: float | None = Query(None, ge=-1.0, le=1.0, description="显性期增长率"),
    safety_discount: float = Query(0.0, ge=0.0, le=1.0, description="额外安全发令"),
):
    """仅返回 DCF 绝对估值结果。"""
    resolved = _resolve_code(code, company)
    if not resolved:
        return err("缺少有效的 6 位股票代码", 400)
    try:
        result = run_valuation(
            resolved,
            "",
            report_type=report_type.strip() or "annual",
            force=force == "1",
            peer_limit=0,
            wacc=wacc,
            terminal_growth=terminal_growth,
            projection_years=projection_years,
            first_stage_growth=first_stage_growth,
            safety_discount=safety_discount,
        )
        if isinstance(result, dict) and result.get("ok"):
            return ok({"dcf": result["data"].get("dcf"), "margin_of_safety_pct": result["data"].get("margin_of_safety_pct")})
        return result
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/stocks/valuation/relative")
def stocks_valuation_relative(
    code: str = Query("", description="股票代码，如 600519"),
    company: str = Query("", description="公司查询串（含 6 位代码即可）；与 code 二选一"),
    report_type: str = Query("annual", description="财报口径：annual 年报 | semi 半年报 | q1 一季报 | q3 三季报"),
    force: str = Query("0", description="1=绕过缓存强制刷新"),
    peer_limit: int = Query(6, ge=0, le=20, description="同业公司上限"),
):
    """仅返回相对估值结果（历史分位 + 同业对比）。"""
    resolved = _resolve_code(code, company)
    if not resolved:
        return err("缺少有效的 6 位股票代码", 400)
    try:
        result = run_valuation(
            resolved,
            "",
            report_type=report_type.strip() or "annual",
            force=force == "1",
            peer_limit=peer_limit,
        )
        if isinstance(result, dict) and result.get("ok"):
            return ok({"relative": result["data"].get("relative"), "verdict": result["data"].get("verdict")})
        return result
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/stocks/valuation/meta")
def stocks_valuation_meta():
    """估值接口元参数说明，供前端构建表单。"""
    return ok(
        {
            "report_types": [
                {"key": "annual", "label": "年报"},
                {"key": "semi", "label": "半年报"},
                {"key": "q1", "label": "一季报"},
                {"key": "q3", "label": "三季报"},
            ],
            "default_assumptions": {
                "wacc": 0.09,
                "terminal_growth": 0.025,
                "projection_years": 5,
                "safety_discount": 0.0,
            },
            "peer_limit_range": [0, 20],
        }
    )
