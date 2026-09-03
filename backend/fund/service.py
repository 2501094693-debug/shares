"""场内基金分类 / 检索门面。"""

from __future__ import annotations

from typing import Any

from core.paths import ensure_cache_dirs
from fund.store import FundStore
from fund import taxonomy


class FundService:
    """ETF / LOF 分类树 + 全市场搜索索引。"""

    def __init__(self) -> None:
        ensure_cache_dirs()
        self.store = FundStore()

    def get_tree(self, *, force_refresh: bool = False) -> list[dict[str, Any]]:
        return self.store.get_tree(force_refresh=force_refresh)

    def get_category_meta(self, code: str) -> dict[str, str] | None:
        return taxonomy.get_category(code)

    def get_category_list(
        self,
        code: str,
        *,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        return self.store.get_category_list(code, force_refresh=force_refresh)

    def search(
        self,
        *,
        name: str = "",
        code: str = "",
        category: str = "",
        market: str = "",
        limit: int = 80,
    ) -> list[dict[str, Any]]:
        self.store.ensure_populated()
        return self.store.search(
            name=name,
            code=code,
            category=category,
            market=market,
            limit=limit,
        )

    def get_by_code(self, code: str) -> dict[str, Any] | None:
        self.store.ensure_populated()
        return self.store.get_by_code(code)

    def get_index_status(self) -> dict[str, Any]:
        return self.store.status()

    def start_build_index(self, *, force: bool = False) -> dict[str, Any]:
        return self.store.start_build(force=force)

    def flat_categories(self) -> list[dict[str, Any]]:
        return taxonomy.flat_categories()


service = FundService()
