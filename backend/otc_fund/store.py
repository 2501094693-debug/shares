"""场外基金代码索引 + 分类排行缓存。"""

from __future__ import annotations

import json
import threading
import time
from collections import defaultdict
from typing import Any

from core.paths import (
    OTC_FUND_INDEX_CACHE,
    OTC_FUND_INDEX_TTL,
    OTC_FUND_RANK_TTL,
    ensure_cache_dirs,
    otc_fund_rank_cache_path,
)
from otc_fund import fetcher, taxonomy


class OtcFundStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._index: dict[str, Any] = {}
        self._by_code: dict[str, dict[str, Any]] = {}
        self._code_prefixes: dict[str, set[str]] = defaultdict(set)
        self._name_chars: dict[str, set[str]] = defaultdict(set)
        self._load_index()

    def _load_index(self) -> None:
        ensure_cache_dirs()
        if not OTC_FUND_INDEX_CACHE.exists():
            return
        try:
            payload = json.loads(OTC_FUND_INDEX_CACHE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if isinstance(payload, dict):
            self._apply_index(payload)

    def _apply_index(self, payload: dict[str, Any]) -> None:
        items = payload.get("items") or []
        if not isinstance(items, list):
            return
        self._index = payload
        self._rebuild_search(items)

    def _rebuild_search(self, items: list[dict[str, Any]]) -> None:
        self._by_code = {}
        self._code_prefixes = defaultdict(set)
        self._name_chars = defaultdict(set)
        for item in items:
            code = str(item.get("code") or "").strip()
            if not code:
                continue
            self._by_code[code] = item
            for i in range(1, len(code) + 1):
                self._code_prefixes[code[:i]].add(code)
            name = str(item.get("name") or "").strip()
            for ch in name:
                self._name_chars[ch].add(code)

    def _index_fresh(self, payload: dict[str, Any] | None) -> bool:
        if not payload:
            return False
        updated = payload.get("updated_at") or ""
        if not updated:
            return False
        try:
            ts = time.mktime(time.strptime(updated, "%Y-%m-%d %H:%M:%S"))
        except ValueError:
            return False
        return (time.time() - ts) < OTC_FUND_INDEX_TTL

    def _read_rank_cache(self, category_code: str, page: int, page_size: int) -> dict[str, Any] | None:
        path = otc_fund_rank_cache_path(category_code, page, page_size)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _write_rank_cache(
        self,
        category_code: str,
        page: int,
        page_size: int,
        payload: dict[str, Any],
    ) -> None:
        ensure_cache_dirs()
        otc_fund_rank_cache_path(category_code, page, page_size).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _rank_fresh(self, payload: dict[str, Any] | None) -> bool:
        if not payload:
            return False
        updated = payload.get("updated_at") or ""
        if not updated:
            return False
        try:
            ts = time.mktime(time.strptime(updated, "%Y-%m-%d %H:%M:%S"))
        except ValueError:
            return False
        return (time.time() - ts) < OTC_FUND_RANK_TTL

    def ensure_index(self, *, force_refresh: bool = False) -> None:
        if not force_refresh and self._by_code and self._index_fresh(self._index):
            return
        if not force_refresh and self._index_fresh(self._index):
            items = self._index.get("items") or []
            if items:
                self._rebuild_search(items)
                return

        items = fetcher.fetch_fund_index()
        payload = {
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "count": len(items),
            "items": items,
        }
        ensure_cache_dirs()
        OTC_FUND_INDEX_CACHE.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        with self._lock:
            self._index = payload
            self._rebuild_search(items)

    def get_tree(self, *, force_refresh: bool = False) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        for code in taxonomy.ALL_CATEGORY_CODES:
            cached = self._read_rank_cache(code, 1, 50)
            if cached and cached.get("total"):
                counts[code] = int(cached["total"])
            elif force_refresh:
                meta = taxonomy.get_category(code)
                if meta is None:
                    continue
                try:
                    counts[code] = fetcher.fetch_category_total(meta["ft"])
                except Exception:  # noqa: BLE001
                    counts[code] = 0
            else:
                counts[code] = 0
        return taxonomy.build_tree(counts)

    def search(
        self,
        *,
        name: str = "",
        code: str = "",
        type_name: str = "",
        limit: int = 80,
    ) -> list[dict[str, Any]]:
        self.ensure_index()
        name = name.strip()
        code = code.strip()
        type_name = type_name.strip()

        items = list(self._by_code.values())
        if type_name:
            items = [item for item in items if type_name in str(item.get("type_name") or "")]

        if code:
            prefix = code
            codes = self._code_prefixes.get(prefix, set())
            if not codes:
                codes = {c for c in self._by_code if c.startswith(prefix)}
            items = [self._by_code[c] for c in codes if c in self._by_code]

        if name:
            matched: set[str] | None = None
            for ch in name:
                hit = self._name_chars.get(ch, set())
                matched = hit if matched is None else matched & hit
                if not matched:
                    break
            if matched is None:
                matched = set()
            items = [self._by_code[c] for c in matched if c in self._by_code]
            items = [item for item in items if name in str(item.get("name") or "")]

        items.sort(key=lambda x: str(x.get("code") or ""))
        return items[: max(1, limit)]

    def get_by_code(self, code: str) -> dict[str, Any] | None:
        self.ensure_index()
        return self._by_code.get(code.strip())

    def get_category_list(
        self,
        category_code: str,
        *,
        page: int = 1,
        page_size: int = 50,
        sort: str = "rzdf",
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        meta = taxonomy.get_category(category_code)
        if meta is None:
            raise KeyError(f"未知场外基金分类: {category_code}")

        if not force_refresh:
            cached = self._read_rank_cache(category_code, page, page_size)
            if self._rank_fresh(cached):
                return cached  # type: ignore[return-value]

        items, total = fetcher.fetch_rank_list(
            meta["ft"],
            category_code,
            page=page,
            page_size=page_size,
            sort=sort,
        )
        payload = {
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "category_code": category_code,
            "category_name": meta.get("name", category_code),
            "page": page,
            "page_size": page_size,
            "total": total,
            "count": len(items),
            "items": items,
        }
        self._write_rank_cache(category_code, page, page_size, payload)
        return payload

    def index_status(self) -> dict[str, Any]:
        return {
            "count": int(self._index.get("count") or len(self._by_code)),
            "updated_at": self._index.get("updated_at") or "",
        }
