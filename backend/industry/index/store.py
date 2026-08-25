"""成分股缓存 + 全市场搜索索引。

磁盘：
  cons/{行业}.json     某个三级行业的成分股（有 TTL）
  stocks_index.json    全市场扁平列表，用来搜股票

流程：启动读磁盘 → 浏览行业时增量写入 → 搜索走倒排 → 不够完整就后台全量扫。

阅读顺序即数据流：
  1. 启动只读磁盘（load_index / rebuild_from_cons_cache）
  2. 浏览行业取成分股（get_constituents）
  3. 写入全局索引（upsert_industry / replace_all）
  4. 检索（search / get_by_code）
  5. 后台把剩余三级行业扫完（start_build）
"""

from __future__ import annotations

import json
import threading
import time
from collections import defaultdict
from typing import Any, Callable

import pandas as pd

from core.paths import (
    CONS_CACHE_DIR,
    CONS_TTL,
    STOCK_INDEX_CACHE,
    cons_cache_path,
    ensure_cache_dirs,
)
from industry.index.cons_fetcher import fetch_third_cons
from industry.index.schema import EMPTY_CELLS, make_index_entry, stock_key

GetL3Meta = Callable[[str], dict[str, Any] | None]
GetL3Codes = Callable[[], list[str]]

_FULL_BUILD_COOLDOWN_SEC = 300


def _cell(row: Any, key: str) -> str:
    """表格一格收成干净字符串。缺列 / NaN / 「—」都当空。"""
    val = row.get(key, "")
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    text = str(val).strip()
    return "" if text in EMPTY_CELLS else text


def _normalize_row(row: Any, meta: dict[str, Any]) -> dict[str, Any]:
    """乐咕一行 → 成分股 dict。

    这里的 ``l1/l2/l3`` 是行业名；写入全局索引时 ``make_index_entry`` 会改成 ``l1_name/...``。
    """
    code = _cell(row, "股票代码")
    return {
        "code": code.split(".")[0] if code else "",
        "full_code": code,
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


def _read_json(path: Any) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _read_cons_cache(l3_code: str) -> dict[str, Any] | None:
    """未过期的行业成分股缓存；过期或损坏返回 None。"""
    path = cons_cache_path(l3_code)
    if not path.exists():
        return None
    data = _read_json(path)
    if not data:
        return None
    age = time.time() - float(data.get("fetched_at") or 0)
    return data if age < CONS_TTL else None


def _write_cons_cache(l3_code: str, payload: dict[str, Any]) -> None:
    ensure_cache_dirs()
    cons_cache_path(l3_code).write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


def _codes(stock: dict[str, Any]) -> tuple[str, str]:
    """(短码, 完整码)，均小写。"""
    short = str(stock.get("code") or "").strip().lower()
    full = str(stock.get("full_code") or "").strip().lower()
    return short, full


class StockStore:
    """成分股仓库 + 搜索索引。

    行业树通过回调注入，避免循环 import：
    ``get_l3_meta(code)`` → 三级行业信息；``get_l3_codes()`` → 全部三级代码。

    内存倒排（下标指向 ``_stocks``）：
    - ``_by_code``        短码 / 完整码 → 下标
    - ``_code_prefixes``  代码前缀 → 下标集合
    - ``_name_chars``     简称每个字 → 下标集合（搜索时取交集再精确过滤）
    """

    def __init__(self, get_l3_meta: GetL3Meta, get_l3_codes: GetL3Codes) -> None:
        self._get_l3_meta = get_l3_meta
        self._get_l3_codes = get_l3_codes

        # 全量扫描会再调 get_constituents，普通 Lock 会自己卡住
        self._lock = threading.RLock()

        self._stocks: list[dict[str, Any]] = []  # 扁平索引

        self._by_code: dict[str, int] = {}  # 代码 → 下标
        self._code_prefixes: dict[str, set[int]] = {}  # "60" → 所有 60 开头
        self._name_chars: dict[str, set[int]] = {}  # "茅" → 简称含茅的下标

        self.ready = False  # 有没有至少一只股票

        self.building = False  # 后台全量是否在跑

        self.complete = False  # 是否覆盖行业树上全部三级

        self.error = ""
        self.progress = {"done": 0, "total": 0}

        self._covered_l3: set[str] = set()  # 已处理过的三级行业
        self.l3_covered = 0
        self.l3_total = 0

        self._last_build_finished_at = 0.0  # 全量结束时间，用来冷却重试

        self.load_index()

    # ------------------------------------------------------------------
    # 1. 启动：只读磁盘，不上网
    # ------------------------------------------------------------------

    def load_index(self) -> None:
        """有总索引就灌进内存；没有则用已有 cons/*.json 拼一份。"""
        ensure_cache_dirs()
        data = _read_json(STOCK_INDEX_CACHE) if STOCK_INDEX_CACHE.exists() else None
        stocks = list((data or {}).get("stocks") or [])
        if not stocks:
            self.rebuild_from_cons_cache()
            return

        raw = (data or {}).get("covered_l3")
        if isinstance(raw, list):
            covered = {str(c).strip() for c in raw if str(c).strip()}
        else:
            # 旧文件没有 covered_l3，只能从股票身上反推
            covered = self._covered_from_stocks(stocks)
        # persist=False：刚读出来，不必立刻写回
        self.replace_all(stocks, persist=False, covered_l3=covered)

    def rebuild_from_cons_cache(self) -> None:
        """扫描各行业成分股缓存，拼成搜索索引（不打网络）。"""
        collected: list[dict[str, Any]] = []
        seen: set[str] = set()
        ensure_cache_dirs()
        for path in CONS_CACHE_DIR.glob("*.json"):
            payload = _read_json(path)
            if not payload:
                continue
            industry = payload.get("industry") or {}
            for s in payload.get("stocks") or []:
                key = stock_key(s)
                if key and key not in seen:
                    seen.add(key)
                    collected.append(make_index_entry(s, industry))
        self.replace_all(collected, persist=bool(collected))

    def replace_all(
            self,
            stocks: list[dict[str, Any]],
            persist: bool = True,
            covered_l3: set[str] | None = None,
    ) -> None:
        """整表替换内存索引。全量结束时应传入 covered_l3。"""
        with self._lock:
            self._stocks = list(stocks)
            self._rebuild_lookups()

            self.ready = bool(self._stocks)
            covered = (
                set(covered_l3)
                if covered_l3 is not None
                else self._covered_from_stocks(self._stocks)
            )
            self._sync_complete(covered)
        # 空列表不落盘，避免把磁盘上还能用的旧索引覆盖掉
        if persist and self._stocks:
            self.save_index()

    def save_index(self) -> None:
        """写入 stocks_index.json。组数据持锁，写文件在锁外，避免堵住搜索。"""
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
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )

    def _rebuild_lookups(self) -> None:
        """按当前 _stocks 重建三张倒排。调用方须已持锁。"""
        by_code: dict[str, int] = {}
        prefixes: dict[str, set[int]] = defaultdict(set)
        chars: dict[str, set[int]] = defaultdict(set)
        for idx, item in enumerate(self._stocks):
            short, full = _codes(item)
            if short:
                by_code[short] = idx
                for i in range(1, len(short) + 1):
                    prefixes[short[:i]].add(idx)
            if full:
                by_code[full] = idx
                body = full.split(".", 1)[0]  # 前缀只用点号前的数字
                for i in range(1, len(body) + 1):
                    prefixes[body[:i]].add(idx)
            for ch in set(str(item.get("name") or "").lower()):
                if not ch.isspace():
                    chars[ch].add(idx)
        self._by_code = by_code
        self._code_prefixes = dict(prefixes)
        self._name_chars = dict(chars)

    def _sync_complete(self, covered: set[str] | None = None) -> None:
        """刷新 complete。须持锁。树还没加载时绝不标成扫完。"""
        if covered is not None:
            self._covered_l3 = {str(c).strip() for c in covered if str(c).strip()}
        try:
            tree = {
                str(c).strip() for c in (self._get_l3_codes() or []) if str(c).strip()
            }
        except Exception:
            tree = set()
        self.l3_total = len(tree)
        if not tree:
            self.l3_covered = len(self._covered_l3)
            self.complete = False
            return
        # 和当前树求交，丢掉缓存里已不存在的旧行业代码
        self.l3_covered = len(self._covered_l3 & tree)
        self.complete = self.l3_covered >= len(tree)

    def _covered_from_stocks(self, stocks: list[dict[str, Any]]) -> set[str]:
        """从股票的 l3_code 收集覆盖集合（看不到「扫过但 0 只股票」的行业）。"""
        out: set[str] = set()
        for s in stocks:
            code = str(s.get("l3_code") or "").strip()
            if code:
                out.add(code)
        return out

    # ------------------------------------------------------------------
    # 2. 浏览行业：取成分股，顺手写入搜索索引
    # ------------------------------------------------------------------

    def get_constituents(
        self,
        code: str,
        force_refresh: bool = False,
        update_index: bool = True,
    ) -> dict[str, Any]:
        """某个三级行业的成分股。全量扫描请传 update_index=False，避免每行业写一次盘。"""
        code = code.strip()
        meta = self._get_l3_meta(code)
        if meta is None:
            raise KeyError(f"未找到三级行业: {code}")

        payload = None if force_refresh else _read_cons_cache(code)
        if payload is None:
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
            self.upsert_industry(meta, payload.get("stocks") or [])

        return payload

    def upsert_industry(self, meta: dict[str, Any], stocks: list[dict[str, Any]]) -> None:
        """把一个行业的股票合并进全局索引（同代码覆盖）。"""
        l3_code = str(meta.get("code") or "").strip()
        with self._lock:
            by_key = {stock_key(s): s for s in self._stocks if stock_key(s)}
            for s in stocks:
                key = stock_key(s)
                if key:
                    by_key[key] = make_index_entry(s, meta)
            self._stocks = list(by_key.values())
            self._rebuild_lookups()
            self.ready = True
            if l3_code:
                self._covered_l3.add(l3_code)
            self._sync_complete()
        self.save_index()

    def find_stock_in_industry(
        self, industry_code: str, code: str
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        """在该行业名单里找一只股票。行业不存在返回 (None, None)。"""
        try:
            data = self.get_constituents(industry_code)
        except KeyError:
            return None, None
        code_l = code.strip().lower()
        hit = None
        for s in data.get("stocks") or []:
            short, full = _codes(s)
            if code_l in {short, full} or code_l in full:
                hit = s
                break
        return (dict(hit) if hit else None), (data.get("industry") or None)

    # ------------------------------------------------------------------
    # 3. 检索
    # ------------------------------------------------------------------

    def ensure_populated(self) -> None:
        """搜索 / 详情前调用：空索引先扫 cons 缓存，不完整则后台补全。"""
        with self._lock:
            empty = not self._stocks
            building = self.building
        if empty:
            self.rebuild_from_cons_cache()
        if not building and self.needs_full_build():
            self.start_build(force=False)

    def get_by_code(self, code: str) -> dict[str, Any] | None:
        """按代码取一条索引（返回拷贝）。"""
        code_l = (code or "").strip().lower()
        if not code_l:
            return None
        with self._lock:
            idx = self._by_code.get(code_l)
            if idx is not None:
                return dict(self._stocks[idx])
            for item in self._stocks:
                short, full = _codes(item)
                # 至少 4 位才允许当完整码子串，避免 "60" 命中所有沪市
                if code_l in {short, full} or (len(code_l) >= 4 and code_l in full):
                    return dict(item)
        return None

    def search(
        self, name: str = "", code: str = "", limit: int = 6000
    ) -> list[dict[str, Any]]:
        """按简称子串、代码前缀检索。两个关键字都空则返回 []。"""
        name_kw = name.strip().lower()
        code_kw = code.strip().lower()
        if not name_kw and not code_kw:
            return []

        with self._lock:
            if not self._stocks:
                return []

            # 只搜代码且精确命中：直接返回
            if code_kw and not name_kw:
                exact = self._by_code.get(code_kw)
                if exact is not None:
                    return [dict(self._stocks[exact])][:limit]

            # 倒排粗筛（代码前缀 ∩ 简称字符）
            candidates: set[int] | None = None
            if code_kw:
                pref = self._code_prefixes.get(code_kw)
                candidates = (
                    set(pref)
                    if pref is not None
                    else {i for k, i in self._by_code.items() if code_kw in k}
                )
            if name_kw:
                parts = [
                    self._name_chars[ch]
                    for ch in set(name_kw)
                    if ch in self._name_chars and not ch.isspace()
                ]
                name_hits = set.intersection(*parts) if parts else set()
                candidates = name_hits if candidates is None else candidates & name_hits
            if not candidates:
                return []

            # 精确过滤：名称必须是连续子串，代码必须出现在短码或完整码里
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

    # ------------------------------------------------------------------
    # 4. 后台全量：把剩余三级行业扫完
    # ------------------------------------------------------------------

    def needs_full_build(self) -> bool:
        """空或不完整，且当前没在跑、距上次结束已过冷却。"""
        with self._lock:
            if self.building:
                return False
            self._sync_complete()  # 行业树可能刚加载完，覆盖率要重算
            if not self._stocks:
                return True
            if self.complete:
                return False
            last = self._last_build_finished_at
            # 个别行业拉取失败时 complete 上不去，没有冷却会反复空转
            return not last or time.time() - last >= _FULL_BUILD_COOLDOWN_SEC

    def start_build(self, force: bool = False) -> dict[str, Any]:
        """开后台线程扫全部三级行业，立刻返回当前状态。"""
        with self._lock:
            if self.building:
                return self.status()
            if not force:
                self._sync_complete()
                if self.complete and self._stocks:
                    return self.status()
        threading.Thread(target=self._run_full_build, daemon=True).start()
        return self.status()

    def status(self) -> dict[str, Any]:
        """给前端进度条 / rebuild API。"""
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

    def _run_full_build(self) -> None:
        """逐行业拉名单（不增量写盘），全部结束后 replace_all 一次。"""
        self.building = True
        self.error = ""
        try:
            codes = list(self._get_l3_codes() or [])
            self.progress = {"done": 0, "total": len(codes)}
            collected: list[dict[str, Any]] = []
            seen: set[str] = set()
            covered: set[str] = set()
            for code in codes:
                try:
                    data = self.get_constituents(code, update_index=False)
                    covered.add(str(code).strip())
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
                except Exception:
                    pass  # 单个行业失败不中断整轮
                self.progress["done"] += 1
            self.replace_all(collected, persist=True, covered_l3=covered)
        except Exception as exc:
            self.error = str(exc)
        finally:
            self._last_build_finished_at = time.time()
            self.building = False
