"""张新民「八看」规则引擎独立接口：拉最新定期报告、只跑 Python，不调用大模型。"""

from __future__ import annotations

import math
from typing import Any

from agent.bazhang_analyst.rules import run_zhang_analysis
from agent.tools.data_fetcher import resolve_company
from agent.tools.financials import fetch_statement_frames


def _jsonable(value: Any) -> Any:
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def public_bazhang_rules(
    *,
    stock: dict[str, str],
    engine: dict[str, Any],
    errors: list[str] | None = None,
) -> dict[str, Any]:
    metrics = engine.get("metrics") or {}
    strategy = metrics.get("strategy") or {}
    return _jsonable(
        {
            "stock_code": stock.get("code") or "",
            "stock_name": stock.get("name") or "",
            "market": stock.get("market") or "",
            "strategy_type": engine.get("strategy_type") or strategy.get("strategy_type") or "未知",
            "strategy_reason": strategy.get("strategy_reason") or "",
            "latest_period": metrics.get("latest_period") or "",
            "period_kind": metrics.get("period_kind") or "",
            "ytd": bool(metrics.get("ytd")),
            "coverage": metrics.get("coverage") or "",
            "period_count": metrics.get("period_count") or 0,
            "annual_count": metrics.get("annual_count") or 0,
            "merged_count": metrics.get("merged_count") or 0,
            "flags": engine.get("flags") or [],
            "tables": engine.get("tables") or {},
            "text": engine.get("text") or "",
            "metrics": metrics,
            "errors": [item for item in (errors or []) if item],
            "data_available": bool(metrics.get("profit") or engine.get("tables")),
        }
    )


def run_bazhang_rules(company: str) -> dict[str, Any]:
    """解析公司 → 强制刷新最新全量定期报告 → 运行规则引擎。不调用 LLM。"""
    stock = resolve_company(company)
    fin = fetch_statement_frames(stock["code"], limit=60, force=True)
    annual = fin.get("annual") or []
    recent = fin.get("recent") or []
    merged = fin.get("merged") or []
    errors = list(fin.get("errors") or [])
    if not merged:
        errors.append("未能获取最新定期报告")
    engine = run_zhang_analysis(annual, recent, merged=merged)
    return public_bazhang_rules(stock=stock, engine=engine, errors=errors)
