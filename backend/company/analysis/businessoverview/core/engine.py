"""业务取数编排：数据采集 → 格式统一。

与数据源无关：所有取数都走 :class:`~company.analysis.businessoverview.core.source.Source`
适配器，引擎内不出现任何 if/else 数据源分支。

本模块只做两件事：

  1. **取数** —— 目前唯一数据源为同花顺 F10 经营分析；
  2. **格式统一** —— 把取到的数据抹平成统一字段契约，见
     :mod:`company.analysis.businessoverview.core.normalize`。

**不做任何二次加工**：不剔除分部行、不合并小业务、不分级、不打标、
不做交叉校验、不生成描述文字、不渲染报告。取到什么就是什么，
只是字段名、类型、单位、日期格式、维度键被统一了。

不依赖任何模型。
"""

from __future__ import annotations

import logging
from typing import Any

from core.codes import normalize_code, safe_str

from company.analysis.businessoverview.core.normalize import normalize_pack
from company.analysis.businessoverview.core.source import Source, get_source

logger = logging.getLogger(__name__)


def _resolve_name(code: str) -> str:
    """用公司画像补简称，失败不阻塞主流程。"""
    try:
        from company.profile import get_stock_profile

        prof = get_stock_profile(code)
        return safe_str((prof.get("stock") or {}).get("name")) or ""
    except Exception:
        return ""


def _pull(source: Source, code: str, latest_n: int, dimension: str) -> dict[str, Any] | None:
    """按适配器取一份数据；失败只记日志，不抛。"""
    try:
        return source.fetch(code, latest_n=latest_n, dimension=dimension)
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s 接入失败 %s: %s", source.label, code, exc)
        return None


def _fetch_primary(
    code: str, *, latest_n: int, dimension: str, primary_key: str
) -> tuple[dict[str, Any] | None, Source]:
    """取数；当前唯一数据源不可用时返回 ``None``。"""
    source = get_source(primary_key)
    pack = _pull(source, code, latest_n, dimension)
    return pack, source


def analyze_business_overview(
    company: str,
    latest_n: int = 2,
    dimension: str = "",
    with_financial: bool = True,
    source: str = "",
) -> dict[str, Any]:
    """取回某公司的主营业务数据（取数 + 格式统一，不做二次加工）。

    参数
    ----
    company
        股票代码或名称。
    latest_n
        取最近 N 个报告期，默认 2。**所有选中期都会原样返回**。
    dimension
        ``1``按产品 / ``2``按行业 / ``3``按地区，留空自动。
    with_financial
        是否附带八看年报经营情况（独立模块的取数结果，不属本引擎派生）。
    source
        数据源 key，留空默认同花顺（当前唯一数据源）。

    返回
    ----
    统一字段契约的字典，字段见
    :data:`~company.analysis.businessoverview.core.normalize.PACK_FIELDS`。
    分部行**一条不少**（二级子项、抵销行、小占比业务均原样保留），
    仅字段名/类型/单位/日期格式/维度键被统一。
    """
    code = normalize_code(safe_str(company)) or safe_str(company)
    if not code:
        raise ValueError("缺少股票代码或名称")

    primary_source = get_source(source)
    primary, primary_source = _fetch_primary(
        code, latest_n=latest_n, dimension=dimension, primary_key=primary_source.key
    )
    if primary is None:
        raise ValueError(f"未获取到 {code} 的主营构成数据")

    profile = normalize_pack(
        primary,
        source_key=primary_source.key,
        source_label=primary_source.label,
        name=_resolve_name(code),
    )

    if with_financial:
        profile["financial"] = _financial_digest(code)

    return profile


def _financial_digest(code: str) -> dict[str, Any]:
    """复用八看引擎取最近年报的经营情况（独立模块，非本引擎派生）。"""
    try:
        from company.analysis.financialreport.engine import analyze

        pack = analyze(code, report_type="annual", limit=60)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}

    return {
        "error": "" if pack.get("data_available") else "无年报口径数据",
        "report_type": pack.get("report_type", "annual"),
        "report_type_label": pack.get("report_type_label", "年报"),
        "latest_period": pack.get("latest_period", ""),
        "coverage": pack.get("coverage", ""),
        "strategy_type": pack.get("strategy_type", ""),
        "flags": pack.get("flags") or [],
        "summary": pack.get("summary") or {},
        "views": pack.get("views") or [],
        "text": pack.get("text", ""),
    }


__all__ = ["analyze_business_overview"]
