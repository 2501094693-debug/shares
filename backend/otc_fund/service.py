"""场外基金检索门面。"""

from __future__ import annotations

from typing import Any

from core.paths import ensure_cache_dirs
from otc_fund import fetcher, taxonomy
from otc_fund.store import OtcFundStore


class OtcFundService:
    def __init__(self) -> None:
        ensure_cache_dirs()
        self.store = OtcFundStore()

    def get_tree(self, *, force_refresh: bool = False) -> list[dict[str, Any]]:
        return self.store.get_tree(force_refresh=force_refresh)

    def flat_categories(self) -> list[dict[str, Any]]:
        return taxonomy.flat_categories()

    def search(
        self,
        *,
        name: str = "",
        code: str = "",
        type_name: str = "",
        limit: int = 80,
    ) -> list[dict[str, Any]]:
        return self.store.search(name=name, code=code, type_name=type_name, limit=limit)

    def get_category_list(
        self,
        category_code: str,
        *,
        page: int = 1,
        page_size: int = 50,
        sort: str = "rzdf",
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        return self.store.get_category_list(
            category_code,
            page=page,
            page_size=page_size,
            sort=sort,
            force_refresh=force_refresh,
        )

    def get_by_code(self, code: str) -> dict[str, Any] | None:
        return self.store.get_by_code(code)

    def get_detail(self, code: str) -> dict[str, Any]:
        meta = self.get_by_code(code)
        nav = fetcher.fetch_latest_nav(code)
        payload = {
            "code": code,
            "name": (meta or {}).get("name", ""),
            "type_name": (meta or {}).get("type_name", ""),
            "pinyin": (meta or {}).get("pinyin", ""),
            **nav,
        }
        return payload

    def get_index_status(self) -> dict[str, Any]:
        return self.store.index_status()

    def warmup_index(self, *, force: bool = False) -> dict[str, Any]:
        self.store.ensure_index(force_refresh=force)
        return self.get_index_status()


service = OtcFundService()
