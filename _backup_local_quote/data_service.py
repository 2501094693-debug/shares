"""数据层门面：对外保持原有 IndustryService API。

模块分工：
- data.core.paths           缓存路径
- data.industry.tree        行业树 / 行业搜索
- data.stocks.schema        索引字段规范
- data.stocks.store         成分股 + 全局股票索引
- data.stocks.quote_fetcher 东财盘口补全（公司详情）
"""

from __future__ import annotations

from typing import Any

from data.core.paths import ensure_cache_dirs
from data.industry.tree import IndustryTree
from data.stocks.quote_fetcher import fetch_stock_quote
from data.stocks.schema import METRIC_KEYS
from data.stocks.store import StockStore


class IndustryService:
    """兼容旧调用方的组合门面。"""

    def __init__(self) -> None:
        ensure_cache_dirs()
        self.tree = IndustryTree()
        self.stocks = StockStore(
            get_l3_meta=self.tree.get_l3_meta,
            get_l3_codes=self.tree.l3_codes,
        )

    # ----- 行业树 -----

    def get_tree(self, force_refresh: bool = False) -> list[dict[str, Any]]:
        return self.tree.get_tree(force_refresh=force_refresh)

    def get_l3_meta(self, code: str) -> dict[str, Any] | None:
        return self.tree.get_l3_meta(code)

    def search(self, keyword: str) -> list[dict[str, Any]]:
        return self.tree.search(keyword)

    # ----- 成分股 / 索引（同一 StockStore） -----

    def get_constituents(
        self,
        code: str,
        force_refresh: bool = False,
        update_index: bool = True,
    ) -> dict[str, Any]:
        return self.stocks.get_constituents(
            code,
            force_refresh=force_refresh,
            update_index=update_index,
        )

    def get_index_status(self) -> dict[str, Any]:
        return self.stocks.status()

    def start_build_stock_index(self, force: bool = False) -> dict[str, Any]:
        return self.stocks.start_build(force=force)

    def search_stocks(
        self, name: str = "", code: str = "", limit: int = 80
    ) -> list[dict[str, Any]]:
        self.stocks.ensure_populated()
        results = self.stocks.search(name=name, code=code, limit=limit)
        # 搜不到且索引不完整时，继续催促全量重建（覆盖「>1000 却缺行业」的旧逻辑）
        if not results and self.stocks.needs_full_build():
            self.stocks.start_build(force=False)
        return results

    def get_stock_profile(
        self, code: str, industry_code: str = "", name: str = ""
    ) -> dict[str, Any]:
        """公司详情：股票指标 + 行业元数据。"""
        code = (code or "").strip()
        if not code:
            raise ValueError("缺少公司代码")

        industry_code = (industry_code or "").strip()
        name = (name or "").strip()

        self.stocks.ensure_populated()
        index_hit = self.stocks.get_by_code(code)

        if not industry_code and index_hit:
            industry_code = str(index_hit.get("l3_code") or "").strip()

        industry_meta = self.tree.get_l3_meta(industry_code) if industry_code else None
        stock: dict[str, Any] | None = None

        if industry_code:
            stock, cons_industry = self.stocks.find_stock_in_industry(
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

        # 东财盘口补全（失败则保留乐咕成分股字段）
        try:
            quote = fetch_stock_quote(str(stock.get("code") or code))
            if quote:
                stock = {**stock, **quote}
        except Exception:  # noqa: BLE001
            pass

        return {"stock": stock, "industry": industry_meta or {}}


service = IndustryService()
