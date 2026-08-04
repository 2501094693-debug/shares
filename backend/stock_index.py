"""全局股票索引：持久化、增量合并、高效检索。

检索结构：
- by_code: 短码 / 完整码 → 条目下标（O(1) 精确）
- code_prefixes: 数字前缀倒排，加速代码前缀/子串候选
- name_chars: 名称字符倒排，缩小名称子串扫描范围
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Callable

from paths import STOCK_INDEX_CACHE, ensure_cache_dirs
from stock_schema import (
    has_price,
    make_index_entry,
    merge_metrics,
    stock_key,
)
from constituents import build_code_lookup, iter_cons_cache_files, read_cons_cache

GetConstituents = Callable[..., dict[str, Any]]
GetL3Codes = Callable[[], list[str]]


class StockIndex:
    """内存股票库 + 磁盘快照 + 后台全量构建。"""

    def __init__(
        self,
        get_constituents: GetConstituents | None = None,
        get_l3_codes: GetL3Codes | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._stocks: list[dict[str, Any]] = []
        self._by_code: dict[str, int] = {}
        self._name_chars: dict[str, set[int]] = {}
        self._code_prefixes: dict[str, set[int]] = {}

        self.ready = False
        self.building = False
        self.error = ""
        self.progress = {"done": 0, "total": 0}

        self._get_constituents = get_constituents
        self._get_l3_codes = get_l3_codes

        ensure_cache_dirs()
        self.load()

    # ------------------------------------------------------------------
    # 状态
    # ------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "ready": self.ready,
                "building": self.building,
                "count": len(self._stocks),
                "progress": dict(self.progress),
                "error": self.error,
            }

    def __len__(self) -> int:
        return len(self._stocks)

    # ------------------------------------------------------------------
    # 加载 / 保存 / 重建内存倒排
    # ------------------------------------------------------------------

    def load(self) -> None:
        if not STOCK_INDEX_CACHE.exists():
            self.rebuild_from_cons_cache()
            return
        try:
            data = json.loads(STOCK_INDEX_CACHE.read_text(encoding="utf-8"))
            stocks = data.get("stocks") or []
        except Exception:  # noqa: BLE001
            stocks = []
        if not stocks:
            self.rebuild_from_cons_cache()
            return
        # 旧快照缺行情时，用 cons 缓存补一轮
        if stocks and not any(has_price(s) for s in stocks[:50]):
            enriched = self._enrich_from_cons(stocks)
            self.replace_all(enriched, persist=True)
        else:
            self.replace_all(stocks, persist=False)

    def save(self) -> None:
        with self._lock:
            payload = {
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "count": len(self._stocks),
                "stocks": self._stocks,
            }
        STOCK_INDEX_CACHE.write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )

    def replace_all(self, stocks: list[dict[str, Any]], persist: bool = True) -> None:
        with self._lock:
            self._stocks = list(stocks)
            self._rebuild_lookups()
            self.ready = len(self._stocks) > 0
        if persist and self._stocks:
            self.save()

    def rebuild_from_cons_cache(self) -> None:
        """扫描 cons/*.json 拼出索引（启动兜底）。"""
        collected: list[dict[str, Any]] = []
        seen: set[str] = set()
        for path in iter_cons_cache_files():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            industry = payload.get("industry") or {}
            for s in payload.get("stocks") or []:
                key = stock_key(s)
                if not key or key in seen:
                    continue
                seen.add(key)
                collected.append(make_index_entry(s, industry))
        self.replace_all(collected, persist=bool(collected))

    def upsert_industry(
        self, meta: dict[str, Any], stocks: list[dict[str, Any]]
    ) -> None:
        """增量合并某行业成分股并落盘。"""
        with self._lock:
            by_key = {stock_key(s): s for s in self._stocks if stock_key(s)}
            for s in stocks:
                key = stock_key(s)
                if not key:
                    continue
                by_key[key] = make_index_entry(s, meta)
            self._stocks = list(by_key.values())
            self._rebuild_lookups()
            self.ready = True
        self.save()

    def _rebuild_lookups(self) -> None:
        by_code: dict[str, int] = {}
        name_chars: dict[str, set[int]] = {}
        code_prefixes: dict[str, set[int]] = {}
        for idx, item in enumerate(self._stocks):
            short = str(item.get("code") or "").strip().lower()
            full = str(item.get("full_code") or "").strip().lower()
            if short:
                by_code[short] = idx
                for i in range(1, len(short) + 1):
                    code_prefixes.setdefault(short[:i], set()).add(idx)
            if full:
                by_code[full] = idx
                # 完整码也挂短前缀（取代码主体）
                body = full.split(".", 1)[0]
                for i in range(1, len(body) + 1):
                    code_prefixes.setdefault(body[:i], set()).add(idx)

            name = str(item.get("name") or "").strip().lower()
            for ch in set(name):
                if ch.isspace():
                    continue
                name_chars.setdefault(ch, set()).add(idx)
        self._by_code = by_code
        self._name_chars = name_chars
        self._code_prefixes = code_prefixes

    # ------------------------------------------------------------------
    # 检索
    # ------------------------------------------------------------------

    def get_by_code(self, code: str) -> dict[str, Any] | None:
        """精确匹配短码或完整码。"""
        code_l = (code or "").strip().lower()
        if not code_l:
            return None
        with self._lock:
            if not self._stocks:
                return None
            idx = self._by_code.get(code_l)
            if idx is not None:
                return dict(self._stocks[idx])
            # 宽松：完整码包含
            for item in self._stocks:
                full = str(item.get("full_code") or "").lower()
                short = str(item.get("code") or "").lower()
                if code_l == short or code_l == full or (code_l in full and len(code_l) >= 4):
                    return dict(item)
        return None

    def search(self, name: str = "", code: str = "", limit: int = 6000) -> list[dict[str, Any]]:
        name_kw = name.strip().lower()
        code_kw = code.strip().lower()
        if not name_kw and not code_kw:
            return []

        with self._lock:
            if not self._stocks:
                return []

            candidates: set[int] | None = None

            if code_kw:
                # 精确命中优先
                exact = self._by_code.get(code_kw)
                if exact is not None and not name_kw:
                    return [dict(self._stocks[exact])][:limit]
                # 前缀倒排：无前缀表时退回全量
                pref = self._code_prefixes.get(code_kw)
                if pref is not None:
                    candidates = set(pref)
                else:
                    # 非纯前缀（中间匹配）时扫 code 键
                    candidates = {
                        idx
                        for key, idx in self._by_code.items()
                        if code_kw in key
                    }

            if name_kw:
                # 取关键词中出现次数最少的字符集合做候选，再做子串确认
                char_sets = [
                    self._name_chars[ch]
                    for ch in set(name_kw)
                    if ch in self._name_chars and not ch.isspace()
                ]
                if not char_sets:
                    name_hits: set[int] = set()
                else:
                    name_hits = set.intersection(*char_sets)
                candidates = (
                    name_hits
                    if candidates is None
                    else candidates.intersection(name_hits)
                )

            if candidates is None:
                return []

            results: list[dict[str, Any]] = []
            # 按名称稳定排序，避免 set 遍历顺序抖动
            ordered = sorted(
                candidates,
                key=lambda i: (
                    str(self._stocks[i].get("name") or ""),
                    str(self._stocks[i].get("code") or ""),
                ),
            )
            for idx in ordered:
                item = self._stocks[idx]
                if name_kw and name_kw not in str(item.get("name") or "").lower():
                    continue
                if code_kw:
                    hay = f"{item.get('code', '')}{item.get('full_code', '')}".lower()
                    if code_kw not in hay:
                        continue
                results.append(dict(item))
                if len(results) >= limit:
                    break
            return results

    def ensure_populated(self) -> None:
        """索引为空时从 cons 兜底；过少时触发后台全量。"""
        with self._lock:
            empty = not self._stocks
            small = len(self._stocks) < 1000
            building = self.building
        if empty:
            self.rebuild_from_cons_cache()
        if small and not building:
            self.start_build(force=False)

    # ------------------------------------------------------------------
    # 全量构建
    # ------------------------------------------------------------------

    def start_build(self, force: bool = False) -> dict[str, Any]:
        with self._lock:
            if self.building:
                return self.status()
            if self.ready and not force and len(self._stocks) > 1000:
                return self.status()
            if self._get_constituents is None or self._get_l3_codes is None:
                return self.status()

        def worker() -> None:
            self.building = True
            self.error = ""
            try:
                codes = self._get_l3_codes()
                self.progress = {"done": 0, "total": len(codes)}
                collected: list[dict[str, Any]] = []
                seen: set[str] = set()
                for code in codes:
                    try:
                        data = self._get_constituents(
                            code, force_refresh=False, notify_index=False
                        )
                        meta = data.get("industry") or {}
                        for s in data.get("stocks") or []:
                            key = stock_key(s)
                            if not key or key in seen:
                                continue
                            seen.add(key)
                            entry = make_index_entry(s, meta)
                            if not entry.get("l3_code"):
                                entry["l3_code"] = code
                            collected.append(entry)
                    except Exception:  # noqa: BLE001
                        pass
                    self.progress["done"] += 1
                self.replace_all(collected, persist=True)
            except Exception as exc:  # noqa: BLE001
                self.error = str(exc)
            finally:
                self.building = False

        threading.Thread(target=worker, daemon=True).start()
        return self.status()

    # ------------------------------------------------------------------
    # 行情补全（启动迁移 / 兜底）
    # ------------------------------------------------------------------

    def _enrich_from_cons(
        self, items: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        cache_by_l3: dict[str, dict[str, dict[str, Any]]] = {}
        out: list[dict[str, Any]] = []
        for item in items:
            if has_price(item):
                out.append(item)
                continue
            l3 = str(item.get("l3_code") or "").strip()
            if l3 not in cache_by_l3:
                payload = read_cons_cache(l3) if l3 else None
                stocks = (payload or {}).get("stocks") or []
                cache_by_l3[l3] = build_code_lookup(stocks)
            lookup = cache_by_l3.get(l3) or {}
            hit = lookup.get(str(item.get("full_code") or "").lower()) or lookup.get(
                str(item.get("code") or "").lower()
            )
            out.append(merge_metrics(item, hit) if hit else item)
        return out
