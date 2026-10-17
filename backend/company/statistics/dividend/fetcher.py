"""分红统一入口（带 TTL 缓存）。

对外主入口 ``get_dividends``，``source`` 可选：

- ``source=eastmoney``（默认）：``scope=detail|history|summary|all``
  - ``scope=detail``   按报告期的结构化分红明细（datacenter ``RPT_SHAREBONUS_DET``）
  - ``scope=history``  F10 逐次分红方案（含预案 / 实施 / 除权除息日）
  - ``scope=summary``  F10 历年现金分红总额 + 增发 / 配股 / IPO 次数
  - ``scope=all``      以上三者合并，并附按年现金分红汇总与摊薄标记
- ``source=ths``：同花顺 F10 分红页，直接给出每次「AH分红总额」
  （含东财缺失的特别分红），附累计分红与按年派现汇总。``scope`` 忽略。
"""

from __future__ import annotations

import time
from typing import Any

from core.cache import TtlCache
from core.codes import normalize_code

from company.statistics.dividend._common import (
    cash_by_year,
    dilution_flags,
    fetch_detail_rows,
    fetch_f10_pack,
    parse_f10_history,
    parse_f10_summary,
)
from company.statistics.dividend.ths import fetch_ths_bonus

DIVIDEND_TTL = 6 * 3600
_cache = TtlCache(DIVIDEND_TTL)

_SCOPES = ("all", "detail", "history", "summary")
_SOURCES = ("eastmoney", "ths")


def _empty(code: str) -> dict[str, Any]:
    return {
        "code": code,
        "name": "",
        "source": "",
        "count": 0,
        "detail": [],
        "history": [],
        "summary": [],
        "cash_by_year": [],
        "dilution": {"seo_num": 0, "allotment_num": 0, "ipo_num": 0, "has_dilution": False},
    }


def _build(code: str, scope: str, limit: int) -> dict[str, Any]:
    norm = normalize_code(code)
    out = _empty(norm)

    if scope in ("all", "detail"):
        detail, meta = fetch_detail_rows(norm, page_size=limit)
        out["detail"] = detail
        if meta:
            out["code"] = meta.get("code") or norm
            out["name"] = meta.get("name") or ""

    if scope in ("all", "history", "summary"):
        pack = fetch_f10_pack(norm)
        if scope in ("all", "history"):
            out["history"] = parse_f10_history(pack)
        if scope in ("all", "summary"):
            out["summary"] = parse_f10_summary(pack)

    if out["detail"]:
        out["cash_by_year"] = cash_by_year(out["detail"])
    if out["summary"]:
        out["dilution"] = dilution_flags(out["summary"])

    out["source"] = "eastmoney" if any(out[key] for key in ("detail", "history", "summary")) else ""
    out["count"] = len(out["detail"]) + len(out["history"]) + len(out["summary"])
    return out


def _has_payload(data: dict[str, Any]) -> bool:
    return bool(data) and int(data.get("count") or 0) > 0


def _build_ths(code: str) -> dict[str, Any]:
    """同花顺口径：按报告期明细（含特别分红）+ 累计 + 按年派现汇总。"""
    data = fetch_ths_bonus(code)
    detail = data.get("detail") or []
    data["count"] = len(detail)
    return data


def get_dividends(
    code: str,
    *,
    scope: str = "all",
    limit: int = 60,
    force: bool = False,
    source: str = "eastmoney",
) -> dict[str, Any]:
    """``source=eastmoney|ths``；东财口径支持 ``scope=all|detail|history|summary``。"""
    src = (source or "eastmoney").strip().lower()
    if src not in _SOURCES:
        raise ValueError(f"source 须为 {' | '.join(_SOURCES)}")
    key = (scope or "all").strip().lower()
    if key not in _SCOPES:
        raise ValueError(f"scope 须为 {' | '.join(_SCOPES)}")
    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")

    if src == "ths":
        cache_key = f"ths:dividend:{norm}"
        now = time.time()
        if not force:
            hit = _cache.get(cache_key)
            if hit is not None:
                return hit
        data = _build_ths(norm)
        if _has_payload(data):
            _cache.put(cache_key, data, cached_at=now)
        return data

    cap = max(1, min(int(limit or 60), 200))
    cache_key = f"em:dividend:{key}:{norm}:{cap}"
    now = time.time()
    if not force:
        hit = _cache.get(cache_key)
        if hit is not None:
            return hit
    data = _build(norm, key, cap)
    if _has_payload(data):
        _cache.put(cache_key, data, cached_at=now)
    return data
