"""场内基金分类列表缓存 + 全局搜索索引。"""

from __future__ import annotations

import json
import threading
import time
from collections import defaultdict
from typing import Any

from core.paths import (
    FUND_INDEX_CACHE,
    FUND_LIST_TTL,
    FUND_TREE_CACHE,
    ensure_cache_dirs,
    fund_list_cache_path,
)
from fund import fetcher, taxonomy


class FundStore:
    """分类列表缓存、分类树、全市场搜索索引。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._index: dict[str, Any] = {}
        self._by_code: dict[str, dict[str, Any]] = {}
        self._code_prefixes: dict[str, set[str]] = defaultdict(set)
        self._name_chars: dict[str, set[str]] = defaultdict(set)
        self._build_lock = threading.Lock()
        self._building = False
        self._load_index()

    def _load_index(self) -> None:
        ensure_cache_dirs()
        if not FUND_INDEX_CACHE.exists():
            return
        try:
            payload = json.loads(FUND_INDEX_CACHE.read_text(encoding="utf-8"))
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

    def _save_index(self) -> None:
        ensure_cache_dirs()
        FUND_INDEX_CACHE.write_text(
            json.dumps(self._index, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _save_tree(self, tree: list[dict[str, Any]]) -> None:
        ensure_cache_dirs()
        payload = {
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "tree": tree,
            "flat": taxonomy.flat_categories(),
        }
        FUND_TREE_CACHE.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _read_category_cache(self, category_code: str) -> dict[str, Any] | None:
        path = fund_list_cache_path(category_code)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _write_category_cache(
        self,
        category_code: str,
        items: list[dict[str, Any]],
        total: int,
    ) -> dict[str, Any]:
        meta = taxonomy.get_category(category_code) or {}
        payload = {
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "category_code": category_code,
            "category_name": meta.get("name", category_code),
            "group_code": meta.get("parent", ""),
            "total": total,
            "count": len(items),
            "items": items,
        }
        ensure_cache_dirs()
        fund_list_cache_path(category_code).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return payload

    def _cache_fresh(self, payload: dict[str, Any] | None) -> bool:
        if not payload:
            return False
        updated = payload.get("updated_at") or ""
        if not updated:
            return False
        try:
            ts = time.mktime(time.strptime(updated, "%Y-%m-%d %H:%M:%S"))
        except ValueError:
            return False
        return (time.time() - ts) < FUND_LIST_TTL

    def get_category_list(
        self,
        category_code: str,
        *,
        force_refresh: bool = False,
        update_index: bool = True,
    ) -> dict[str, Any]:
        meta = taxonomy.get_category(category_code)
        if meta is None:
            raise KeyError(f"未知基金分类: {category_code}")

        if not force_refresh:
            cached = self._read_category_cache(category_code)
            if self._cache_fresh(cached):
                if update_index:
                    self._merge_items(cached.get("items") or [])
                return cached  # type: ignore[return-value]

        items, total = fetcher.fetch_category_list(meta["fs"], category_code)
        payload = self._write_category_cache(category_code, items, total)
        if update_index:
            self._merge_items(items)
        return payload

    def _merge_items(self, items: list[dict[str, Any]]) -> None:
        if not items:
            return
        with self._lock:
            existing = {
                str(item.get("code") or "").strip(): item
                for item in (self._index.get("items") or [])
                if str(item.get("code") or "").strip()
            }
            for item in items:
                code = str(item.get("code") or "").strip()
                if code:
                    existing[code] = item
            merged = list(existing.values())
            merged.sort(key=lambda x: str(x.get("code") or ""))
            self._index = {
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "count": len(merged),
                "complete": self._index.get("complete", False),
                "items": merged,
            }
            self._rebuild_search(merged)
            self._save_index()

    def get_tree(self, *, force_refresh: bool = False) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        if not force_refresh and FUND_TREE_CACHE.exists():
            try:
                cached = json.loads(FUND_TREE_CACHE.read_text(encoding="utf-8"))
                tree = cached.get("tree")
                if isinstance(tree, list) and tree:
                    return tree
            except (OSError, json.JSONDecodeError):
                pass

        for code in taxonomy.ALL_CATEGORY_CODES:
            meta = taxonomy.get_category(code)
            if meta is None:
                continue
            cached = self._read_category_cache(code)
            if self._cache_fresh(cached):
                counts[code] = int(cached.get("count") or 0)
            else:
                try:
                    counts[code] = fetcher.fetch_category_total(meta["fs"])
                except Exception:  # noqa: BLE001
                    counts[code] = int((cached or {}).get("count") or 0)

        tree = taxonomy.build_tree(counts)
        self._save_tree(tree)
        return tree

    def search(
        self,
        *,
        name: str = "",
        code: str = "",
        category: str = "",
        market: str = "",
        limit: int = 80,
    ) -> list[dict[str, Any]]:
        name = name.strip()
        code = code.strip()
        category = category.strip()
        market = market.strip().upper()

        items = list(self._by_code.values())
        if category:
            items = [item for item in items if item.get("category_code") == category]
        if market in {"SH", "SZ"}:
            items = [item for item in items if item.get("market") == market]

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

        items.sort(
            key=lambda x: (
                x.get("category_code") or "",
                x.get("code") or "",
            )
        )
        return items[: max(1, limit)]

    def get_by_code(self, code: str) -> dict[str, Any] | None:
        return self._by_code.get(code.strip())

    def status(self) -> dict[str, Any]:
        return {
            "count": int(self._index.get("count") or len(self._by_code)),
            "complete": bool(self._index.get("complete")),
            "updated_at": self._index.get("updated_at") or "",
            "categories": len(taxonomy.ALL_CATEGORY_CODES),
        }

    def start_build(self, *, force: bool = False) -> dict[str, Any]:
        with self._build_lock:
            if self._building and not force:
                return {**self.status(), "building": True}
            self._building = True

        def _run() -> None:
            try:
                all_items: list[dict[str, Any]] = []
                for category_code in taxonomy.ALL_CATEGORY_CODES:
                    payload = self.get_category_list(
                        category_code,
                        force_refresh=force,
                        update_index=False,
                    )
                    all_items.extend(payload.get("items") or [])
                with self._lock:
                    self._index = {
                        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "count": len(all_items),
                        "complete": True,
                        "items": all_items,
                    }
                    self._rebuild_search(all_items)
                    self._save_index()
                counts = {
                    code: int((self._read_category_cache(code) or {}).get("count") or 0)
                    for code in taxonomy.ALL_CATEGORY_CODES
                }
                self._save_tree(taxonomy.build_tree(counts))
            finally:
                with self._build_lock:
                    self._building = False

        if force or not self._index.get("complete"):
            thread = threading.Thread(target=_run, daemon=True, name="fund-index-build")
            thread.start()
        return {**self.status(), "building": True}

    def ensure_populated(self) -> None:
        if self._by_code:
            return
        if self._index.get("items"):
            self._rebuild_search(self._index["items"])
            return
        self.start_build(force=False)
