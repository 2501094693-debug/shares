"""申万分类 / 检索门面。

行业树 + 具体公司索引。个股盘口、K 线、资讯不在这里。
"""

from __future__ import annotations

from typing import Any

from core.paths import ensure_cache_dirs
from industry.stocks import StockStore
from industry.tree import IndustryTree


class IndustryService:
    """行业树 + 全市场股票索引。"""

    def __init__(self) -> None:
        ensure_cache_dirs()
        self.tree = IndustryTree()
        self.stocks = StockStore(
            get_l3_meta=self.tree.get_l3_meta,
            get_l3_codes=self.tree.l3_codes,
        )

    def get_tree(self, force_refresh: bool = False) -> list[dict[str, Any]]:
        return self.tree.get_tree(force_refresh=force_refresh)

    def get_l3_meta(self, code: str) -> dict[str, Any] | None:
        return self.tree.get_l3_meta(code)

    def search(self, keyword: str) -> list[dict[str, Any]]:
        return self.tree.search(keyword)

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
        if not results and self.stocks.needs_full_build():
            self.stocks.start_build(force=False)
        return results


service = IndustryService()
