"""数据层门面：对外保持原有 IndustryService API，内部按职责拆分。

模块分工：
- paths          缓存路径
- stock_schema   索引字段规范
- industry_tree  行业树 / 行业搜索
- constituents   成分股拉取与缓存
- stock_index    全局股票索引与高效检索
"""

from __future__ import annotations

from typing import Any

from stock_schema import METRIC_KEYS
from constituents import ConstituentsRepo
from industry_tree import IndustryTree
from paths import ensure_cache_dirs
from stock_index import StockIndex


class IndustryService:
    """兼容旧调用方的组合门面。"""

    def __init__(self) -> None:
        ensure_cache_dirs()
        self.tree = IndustryTree()
        self.index = StockIndex()
        self.cons = ConstituentsRepo(
            get_l3_meta=self.tree.get_l3_meta,
            on_updated=self.index.upsert_industry,
        )
        # 全量构建依赖成分股与行业代码列表（延迟注入，避免循环构造）
        self.index._get_constituents = self.cons.get
        self.index._get_l3_codes = self.tree.l3_codes

    # ----- 行业树 -----

    def get_tree(self, force_refresh: bool = False) -> list[dict[str, Any]]:
        return self.tree.get_tree(force_refresh=force_refresh)

    def get_l3_meta(self, code: str) -> dict[str, Any] | None:
        return self.tree.get_l3_meta(code)

    def search(self, keyword: str) -> list[dict[str, Any]]:
        return self.tree.search(keyword)

    # ----- 成分股 -----

    def get_constituents(
        self,
        code: str,
        force_refresh: bool = False,
        update_index: bool = True,
    ) -> dict[str, Any]:
        return self.cons.get(
            code,
            force_refresh=force_refresh,
            notify_index=update_index,
        )

    # ----- 股票索引 -----

    def get_index_status(self) -> dict[str, Any]:
        return self.index.status()

    def start_build_stock_index(self, force: bool = False) -> dict[str, Any]:
        return self.index.start_build(force=force)

    def search_stocks(
        self, name: str = "", code: str = "", limit: int = 80
    ) -> list[dict[str, Any]]:
        self.index.ensure_populated()
        return self.index.search(name=name, code=code, limit=limit)

    def get_stock_profile(
        self, code: str, industry_code: str = "", name: str = ""
    ) -> dict[str, Any]:
        """公司详情：股票指标 + 行业元数据。"""
        code = (code or "").strip()
        if not code:
            raise ValueError("缺少公司代码")

        industry_code = (industry_code or "").strip()
        name = (name or "").strip()

        self.index.ensure_populated()
        index_hit = self.index.get_by_code(code)

        if not industry_code and index_hit:
            industry_code = str(index_hit.get("l3_code") or "").strip()

        industry_meta = self.tree.get_l3_meta(industry_code) if industry_code else None
        stock: dict[str, Any] | None = None

        if industry_code:
            stock, cons_industry = self.cons.find_stock_in_industry(industry_code, code)
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

        return {"stock": stock, "industry": industry_meta or {}}


service = IndustryService()
