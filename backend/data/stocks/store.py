"""成分股缓存 + 全局股票索引（同一类）。

职责：
1. 按三级行业拉取 / 缓存成分股；
2. 维护全局扁平索引与倒排，支持名称 / 代码检索；
3. 浏览行业时增量合并，后台可全量重建。
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Callable

import pandas as pd

from data.core.paths import (
    CONS_CACHE_DIR,
    CONS_TTL,
    STOCK_INDEX_CACHE,
    cons_cache_path,
    ensure_cache_dirs,
)
from data.stocks.cons_fetcher import fetch_third_cons
from data.stocks.schema import make_index_entry, stock_key

GetL3Meta = Callable[[str], dict[str, Any] | None]
GetL3Codes = Callable[[], list[str]]


def _cell(row: Any, key: str) -> str:
    val = row.get(key, "")
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    text = str(val).strip()
    return "" if text in {"nan", "None", "—", "-", "<NA>"} else text


def _normalize_row(row: Any, meta: dict[str, Any]) -> dict[str, Any]:
    stock_code = _cell(row, "股票代码")
    short_code = stock_code.split(".")[0] if stock_code else ""
    return {
        "code": short_code,
        "full_code": stock_code,
        "name": _cell(row, "股票简称"),
        "l1": meta.get("l1_name", ""),
        "l2": meta.get("l2_name", ""),
        "l3": _cell(row, "申万3级") or meta.get("name", ""),
        "include_date": _cell(row, "纳入时间"),
        "price": _cell(row, "价格"),
        "pe": _cell(row, "市盈率"),
        "pe_ttm": _cell(row, "市盈率ttm"),
        "pb": _cell(row, "市净率"),
        "roe": _cell(row, "ROE"),
        "dividend_yield": _cell(row, "股息率"),
        "market_cap": _cell(row, "市值"),
        "change_1d": _cell(row, "近1日涨幅"),
        "change_5d": _cell(row, "近5日涨幅"),
        "change_ytd": _cell(row, "今年以来涨幅"),
        "profit_growth": _cell(row, "净利润增速"),
        "revenue_growth": _cell(row, "营收增速"),
    }


def _read_cons_cache(l3_code: str) -> dict[str, Any] | None:
    path = cons_cache_path(l3_code)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _write_cons_cache(l3_code: str, payload: dict[str, Any]) -> None:
    ensure_cache_dirs()
    cons_cache_path(l3_code).write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


def _build_code_lookup(stocks: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for s in stocks:
        full = str(s.get("full_code") or "").strip().lower()
        short = str(s.get("code") or "").strip().lower()
        if full:
            lookup[full] = s
        if short:
            lookup[short] = s
    return lookup


class StockStore:
    """成分股仓库 + 全局搜索索引。"""

    def __init__(
        self,
        get_l3_meta: GetL3Meta,
        get_l3_codes: GetL3Codes,
    ) -> None:
        self._get_l3_meta = get_l3_meta
        self._get_l3_codes = get_l3_codes

        self._lock = threading.RLock()
        self._stocks: list[dict[str, Any]] = []
        self._by_code: dict[str, int] = {}
        self._name_chars: dict[str, set[int]] = {}
        self._code_prefixes: dict[str, set[int]] = {}

        self.ready = False
        self.building = False
        self.complete = False
        self.error = ""
        self.progress = {"done": 0, "total": 0}
        self._covered_l3: set[str] = set()
        self.l3_covered = 0
        self.l3_total = 0
        self._last_build_finished_at = 0.0

        ensure_cache_dirs()
        self.load_index()

    # ==================================================================
    # 成分股
    # ==================================================================

    def get_constituents(
        self,
        code: str,
        force_refresh: bool = False,
        update_index: bool = True,
    ) -> dict[str, Any]:
        """获取三级行业成分股；可选同步进全局索引。"""
        code = code.strip()
        meta = self._get_l3_meta(code)
        if meta is None:
            raise KeyError(f"未找到三级行业: {code}")

        if not force_refresh:
            cached = _read_cons_cache(code)
            if cached and time.time() - cached.get("fetched_at", 0) < CONS_TTL:
                if update_index:
                    self.upsert_industry(meta, cached.get("stocks") or [])
                return cached

        df = fetch_third_cons(code)
        stocks = [_normalize_row(row, meta) for _, row in df.iterrows()]
        payload = {
            "industry": meta,
            "count": len(stocks),
            "stocks": stocks,
            "fetched_at": time.time(),
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        _write_cons_cache(code, payload)
        if update_index:
            self.upsert_industry(meta, stocks)
        return payload

    def find_stock_in_industry(
        self, industry_code: str, code: str
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        """在指定行业成分股中查找股票 → (stock, industry_meta)。"""
        try:
            data = self.get_constituents(
                industry_code, force_refresh=False, update_index=True
            )
        except KeyError:
            return None, None
        code_l = code.strip().lower()
        lookup = _build_code_lookup(data.get("stocks") or [])
        hit = lookup.get(code_l)
        if hit is None:
            for s in data.get("stocks") or []:
                full = str(s.get("full_code") or "").lower()
                if code_l == str(s.get("code") or "").lower() or code_l in full:
                    hit = s
                    break
        return (dict(hit) if hit else None), (data.get("industry") or None)

    # ==================================================================
    # 索引：状态 / 加载 / 保存
    # ==================================================================

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "ready": self.ready,
                "building": self.building,
                "complete": self.complete,
                "count": len(self._stocks),
                "l3_covered": self.l3_covered,
                "l3_total": self.l3_total,
                "progress": dict(self.progress),
                "error": self.error,
            }

    def __len__(self) -> int:
        return len(self._stocks)

    def _sync_complete_unlocked(self, covered: set[str] | None = None) -> None:
        """根据已覆盖三级行业数判断索引是否完整（须持锁）。"""
        if covered is not None:
            self._covered_l3 = {str(c).strip() for c in covered if str(c).strip()}
        try:
            total_codes = {
                str(c).strip() for c in (self._get_l3_codes() or []) if str(c).strip()
            }
        except Exception:  # noqa: BLE001
            total_codes = set()
        self.l3_total = len(total_codes)
        if total_codes:
            self.l3_covered = len(self._covered_l3 & total_codes)
            self.complete = self.l3_covered >= len(total_codes)
        else:
            self.l3_covered = len(self._covered_l3)
            # 行业树尚未就绪时，不把半成品标成 complete
            self.complete = False

    def replace_all(
        self,
        stocks: list[dict[str, Any]],
        persist: bool = True,
        covered_l3: set[str] | None = None,
    ) -> None:
        with self._lock:
            self._stocks = list(stocks)
            self._rebuild_lookups()
            self.ready = len(self._stocks) > 0
            covered = (
                set(covered_l3)
                if covered_l3 is not None
                else self._covered_from_stocks(self._stocks)
            )
            self._sync_complete_unlocked(covered)
        if persist and self._stocks:
            self.save_index()

    def load_index(self) -> None:
        if not STOCK_INDEX_CACHE.exists():
            self.rebuild_from_cons_cache()
            return
        try:
            data = json.loads(STOCK_INDEX_CACHE.read_text(encoding="utf-8"))
            stocks = data.get("stocks") or []
        except Exception:  # noqa: BLE001
            stocks = []
            data = {}
        if not stocks:
            self.rebuild_from_cons_cache()
            return
        covered_raw = data.get("covered_l3")
        covered = (
            {str(c).strip() for c in covered_raw if str(c).strip()}
            if isinstance(covered_raw, list)
            else self._covered_from_stocks(stocks)
        )
        self.replace_all(stocks, persist=False, covered_l3=covered)

    def save_index(self) -> None:
        with self._lock:
            payload = {
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "count": len(self._stocks),
                "complete": self.complete,
                "l3_covered": self.l3_covered,
                "l3_total": self.l3_total,
                "covered_l3": sorted(self._covered_l3),
                "stocks": self._stocks,
            }
        STOCK_INDEX_CACHE.write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )

    def _covered_from_stocks(self, stocks: list[dict[str, Any]]) -> set[str]:
        out: set[str] = set()
        for s in stocks:
            code = str(s.get("l3_code") or "").strip()
            if code:
                out.add(code)
        return out

    def rebuild_from_cons_cache(self) -> None:
        """扫描 cons/*.json 拼出索引（启动兜底）。"""
        collected: list[dict[str, Any]] = []
        seen: set[str] = set()
        ensure_cache_dirs()
        for path in CONS_CACHE_DIR.glob("*.json"):
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
        l3_code = str(meta.get("code") or "").strip()
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
            if l3_code:
                self._covered_l3.add(l3_code)
            self._sync_complete_unlocked()
        self.save_index()

    def needs_full_build(self) -> bool:
        """索引未覆盖全部三级行业时需要全量重建。"""
        with self._lock:
            if self.building:
                return False
            # 先按当前行业树刷新完整度（启动时树可能尚未加载）
            self._sync_complete_unlocked()
            if not self._stocks:
                return True
            if self.complete:
                return False
            # 全量跑完仍缺行业时，避免因个别拉取失败而疯狂重试
            if (
                self._last_build_finished_at
                and time.time() - self._last_build_finished_at < 300
            ):
                return False
            return True

    def ensure_populated(self) -> None:
        with self._lock:
            empty = not self._stocks
            building = self.building
        if empty:
            self.rebuild_from_cons_cache()
        if self.needs_full_build() and not building:
            self.start_build(force=False)

    # ==================================================================
    # 索引：全量构建（直接调本类 get_constituents，无需注入）
    # ==================================================================

    def start_build(self, force: bool = False) -> dict[str, Any]:
        with self._lock:
            if self.building:
                return self.status()
            if not force:
                self._sync_complete_unlocked()
                if self.complete and self._stocks:
                    return self.status()

        def worker() -> None:
            self.building = True
            self.error = ""
            try:
                codes = self._get_l3_codes()
                self.progress = {"done": 0, "total": len(codes)}
                collected: list[dict[str, Any]] = []
                seen: set[str] = set()
                covered: set[str] = set()
                for code in codes:
                    try:
                        data = self.get_constituents(
                            code, force_refresh=False, update_index=False
                        )
                        meta = data.get("industry") or {}
                        covered.add(str(code).strip())
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
                self.replace_all(collected, persist=True, covered_l3=covered)
            except Exception as exc:  # noqa: BLE001
                self.error = str(exc)
            finally:
                self._last_build_finished_at = time.time()
                self.building = False

        threading.Thread(target=worker, daemon=True).start()
        return self.status()

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

    # ==================================================================
    # 索引：检索
    # ==================================================================

    def get_by_code(self, code: str) -> dict[str, Any] | None:
        code_l = (code or "").strip().lower()
        if not code_l:
            return None
        with self._lock:
            if not self._stocks:
                return None
            idx = self._by_code.get(code_l)
            if idx is not None:
                return dict(self._stocks[idx])
            for item in self._stocks:
                full = str(item.get("full_code") or "").lower()
                short = str(item.get("code") or "").lower()
                if code_l == short or code_l == full or (
                    code_l in full and len(code_l) >= 4
                ):
                    return dict(item)
        return None

    def search(
        self, name: str = "", code: str = "", limit: int = 6000
    ) -> list[dict[str, Any]]:
        name_kw = name.strip().lower()
        code_kw = code.strip().lower()
        if not name_kw and not code_kw:
            return []

        with self._lock:
            if not self._stocks:
                return []

            candidates: set[int] | None = None

            if code_kw:
                exact = self._by_code.get(code_kw)
                if exact is not None and not name_kw:
                    return [dict(self._stocks[exact])][:limit]
                pref = self._code_prefixes.get(code_kw)
                if pref is not None:
                    candidates = set(pref)
                else:
                    candidates = {
                        idx
                        for key, idx in self._by_code.items()
                        if code_kw in key
                    }

            if name_kw:
                char_sets = [
                    self._name_chars[ch]
                    for ch in set(name_kw)
                    if ch in self._name_chars and not ch.isspace()
                ]
                name_hits: set[int] = (
                    set.intersection(*char_sets) if char_sets else set()
                )
                candidates = (
                    name_hits
                    if candidates is None
                    else candidates.intersection(name_hits)
                )

            if candidates is None:
                return []

            results: list[dict[str, Any]] = []
            ordered = sorted(
                candidates,
                key=lambda i: (
                    str(self._stocks[i].get("code") or ""),
                    str(self._stocks[i].get("name") or ""),
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
