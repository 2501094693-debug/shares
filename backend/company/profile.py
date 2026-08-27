"""公司详情页：索引里的行业归属 + 实时盘口。"""

from __future__ import annotations

from typing import Any

from company.statistics import fetch_live_quote, fetch_stock_quote
from industry.index import METRIC_KEYS
from industry.service import service as industry


def get_stock_profile(
    code: str,
    industry_code: str = "",
    name: str = "",
    *,
    force_quote: bool = False,
    live_only: bool = False,
) -> dict[str, Any]:
    """股票指标 + 申万行业元数据。"""
    code = (code or "").strip()
    if not code:
        raise ValueError("缺少公司代码")

    industry_code = (industry_code or "").strip()
    name = (name or "").strip()

    industry.stocks.ensure_populated()
    index_hit = industry.stocks.get_by_code(code)

    if not industry_code and index_hit:
        industry_code = str(index_hit.get("l3_code") or "").strip()

    industry_meta = industry.tree.get_l3_meta(industry_code) if industry_code else None
    stock: dict[str, Any] | None = None

    if industry_code:
        stock, cons_industry = industry.stocks.find_stock_in_industry(
            industry_code, code
        )
        if industry_meta is None and cons_industry:
            industry_meta = cons_industry

    if stock is None and index_hit:
        stock = {
            "code": index_hit.get("code") or code,
            "full_code": index_hit.get("full_code") or "",
            "name": index_hit.get("name") or name or code,
            "include_date": index_hit.get("include_date") or "",
            "l1_name": index_hit.get("l1_name") or "",
            "l2_name": index_hit.get("l2_name") or "",
            "l3_name": index_hit.get("l3_name") or "",
            "l3_code": index_hit.get("l3_code") or industry_code,
        }
        for key in METRIC_KEYS:
            if index_hit.get(key) is not None:
                stock[key] = index_hit.get(key, "")

    if stock is None:
        stock = {"code": code, "full_code": "", "name": name or code}

    if industry_meta is None and index_hit:
        industry_meta = {
            "code": index_hit.get("l3_code") or "",
            "name": index_hit.get("l3_name") or "",
            "l1_name": index_hit.get("l1_name") or "",
            "l2_name": index_hit.get("l2_name") or "",
        }

    try:
        quote_fn = fetch_live_quote if live_only else fetch_stock_quote
        quote = quote_fn(str(stock.get("code") or code), force=force_quote)
        if quote:
            stock = {**stock, **quote}
            stock["quote_ready"] = True
            if not stock.get("dividend_ttm"):
                try:
                    price = float(
                        str(stock.get("price") or "").replace(",", "").strip()
                    )
                    dy = float(
                        str(stock.get("dividend_yield") or "")
                        .replace("%", "")
                        .replace(",", "")
                        .strip()
                    )
                    if price > 0 and dy == dy:
                        stock["dividend_ttm"] = f"{price * dy / 100:.2f}"
                except (TypeError, ValueError):
                    pass
        else:
            stock["quote_ready"] = False
    except Exception:  # noqa: BLE001
        stock["quote_ready"] = False

    return {"stock": stock, "industry": industry_meta or {}}
