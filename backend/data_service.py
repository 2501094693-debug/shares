"""申万三级行业数据服务：拉取并缓存行业树与成分股。

本模块是后端的数据层核心，对 Flask API（app.py）屏蔽外部数据源细节。
主要职责：
1. 构建 / 缓存申万一级 → 二级 → 三级行业树；
2. 按三级行业代码拉取并缓存成分股列表；
3. 维护全局股票索引，支持按名称 / 代码跨行业搜索。

数据源：
- 行业树：akshare（sw_index_*_info）
- 成分股：cons_fetcher（爬取乐咕乐股 HTML，规避 akshare 列名问题）

缓存目录（相对本文件）：
- cache/industry_tree.json  —— 整棵行业树 + 扁平三级列表
- cache/cons/*.json         —— 各三级行业成分股（带 TTL）
- cache/stocks_index.json   —— 全局股票索引
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

import akshare as ak
import pandas as pd

from cons_fetcher import fetch_third_cons

# ---------------------------------------------------------------------------
# 缓存路径与常量
# ---------------------------------------------------------------------------

# 所有磁盘缓存的根目录：backend/cache/
CACHE_DIR = Path(__file__).resolve().parent / "cache"
# 行业树缓存：含 tree（嵌套结构）与 flat_l3（按 code 扁平查找）
TREE_CACHE = CACHE_DIR / "industry_tree.json"
# 成分股按行业拆分存储，文件名由行业代码中的 '.' 替换为 '_'
CONS_CACHE_DIR = CACHE_DIR / "cons"
# 全局股票索引：供 search_stocks 做名称/代码检索
STOCK_INDEX_CACHE = CACHE_DIR / "stocks_index.json"

# 成分股缓存有效期（秒）。过期后下次请求会重新打外部接口。
# 6 小时可在数据新鲜度与请求频率之间取得平衡。
CONS_TTL = 6 * 60 * 60


class IndustryService:
    """申万行业数据服务（进程内单例使用，见模块末尾 service）。

    内存状态说明：
    - _tree: 一级行业列表，每级节点含 children，供前端树形展示
    - _flat_l3: 三级行业 code → 元数据，供搜索与成分股关联
    - _stock_index: 扁平股票列表（含一二三级归属），供全局搜股
    - _index_*: 索引构建状态，供前端轮询进度
    """

    def __init__(self) -> None:
        # 保护 get_tree / _build_tree，避免并发首次加载时重复打 akshare
        self._lock = threading.Lock()

        # 行业树内存缓存；None 表示尚未加载
        self._tree: list[dict[str, Any]] | None = None
        # 三级行业扁平索引：{ "850111.SI": {code, name, l1_*, l2_*, count}, ... }
        self._flat_l3: dict[str, dict[str, Any]] = {}

        # 全局股票索引及构建状态
        self._stock_index: list[dict[str, Any]] = []
        self._index_ready = False  # 是否已有可用索引（非空）
        self._index_building = False  # 后台全量构建是否进行中
        self._index_error = ""  # 最近一次全量构建失败原因
        self._index_progress = {"done": 0, "total": 0}  # 已处理 / 总三级行业数

        # 确保缓存目录存在，然后尝试从磁盘恢复股票索引
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        CONS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self._load_stock_index_from_disk()

    # -----------------------------------------------------------------------
    # 行业树
    # -----------------------------------------------------------------------

    def get_tree(self, force_refresh: bool = False) -> list[dict[str, Any]]:
        """获取申万行业树（一级 → 二级 → 三级）。

        读取优先级（force_refresh=False 时）：
        1. 内存 _tree
        2. 磁盘 industry_tree.json
        3. 调用 akshare 重建（_build_tree）

        Args:
            force_refresh: 为 True 时跳过内存与磁盘，强制远程重建。
                对应 API：GET /api/industries?refresh=1

        Returns:
            一级行业节点列表，节点结构大致为：
            {code, name, count, children: [{..., children: [{code, name, count}]}]}
        """
        with self._lock:
            # 1) 内存命中
            if self._tree is not None and not force_refresh:
                return self._tree
            # 2) 磁盘命中：同时恢复扁平三级表，供 search / get_l3_meta 使用
            if TREE_CACHE.exists() and not force_refresh:
                data = json.loads(TREE_CACHE.read_text(encoding="utf-8"))
                self._tree = data["tree"]
                self._flat_l3 = {item["code"]: item for item in data["flat_l3"]}
                return self._tree
            # 3) 远程重建
            return self._build_tree()

    def _build_tree(self) -> list[dict[str, Any]]:
        """从 akshare 拉取一二三级行业，组装嵌套树并落盘。

        组装策略：
        - 先建 L1 列表，并用名称做父节点查找表（akshare 用「上级行业」名称关联）；
        - 再建 L2，挂到对应 L1.children，临时保留 parent_name；
        - 再建 L3：既写入 flat_l3（带完整一二三级元数据），也挂到 L2.children；
        - 最后去掉 L2 上仅用于组装的 parent_name 字段。

        注意：调用方需已持有 self._lock（由 get_tree 保证）。
        """
        # 分别拉取申万一、二、三级行业基础信息表
        l1_df = ak.sw_index_first_info()
        l2_df = ak.sw_index_second_info()
        l3_df = ak.sw_index_third_info()

        # 统一清洗列名空白，避免「行业代码」等字段匹配失败
        for df in (l1_df, l2_df, l3_df):
            df.columns = [str(c).strip() for c in df.columns]

        # ---------- 一级行业 ----------
        l1_list: list[dict[str, Any]] = []
        for _, row in l1_df.iterrows():
            code = str(row["行业代码"]).strip()
            name = str(row["行业名称"]).strip()
            # 成份个数可能为空，缺省为 0
            count = int(row["成份个数"]) if pd.notna(row.get("成份个数")) else 0
            l1_list.append(
                {
                    "code": code,
                    "name": name,
                    "count": count,
                    "children": [],  # 稍后挂载二级
                }
            )

        # 按名称索引一级，供二级通过「上级行业」字段挂载
        l1_by_name = {item["name"]: item for item in l1_list}

        # ---------- 二级行业 ----------
        l2_list: list[dict[str, Any]] = []
        for _, row in l2_df.iterrows():
            code = str(row["行业代码"]).strip()
            name = str(row["行业名称"]).strip()
            parent_name = str(row.get("上级行业", "")).strip()
            count = int(row["成份个数"]) if pd.notna(row.get("成份个数")) else 0
            node = {
                "code": code,
                "name": name,
                "parent_name": parent_name,  # 组装期临时字段，写盘前会删除
                "count": count,
                "children": [],  # 稍后挂载三级
            }
            l2_list.append(node)
            parent = l1_by_name.get(parent_name)
            if parent is not None:
                parent["children"].append(node)

        # 按名称索引二级，供三级挂载，并反查一级信息
        l2_by_name = {item["name"]: item for item in l2_list}
        flat_l3: list[dict[str, Any]] = []

        # ---------- 三级行业 ----------
        for _, row in l3_df.iterrows():
            code = str(row["行业代码"]).strip()
            name = str(row["行业名称"]).strip()
            parent_name = str(row.get("上级行业", "")).strip()  # 实为二级行业名
            count = int(row["成份个数"]) if pd.notna(row.get("成份个数")) else 0

            l2_node = l2_by_name.get(parent_name)
            # 通过二级节点反查所属一级
            l1_name = l2_node["parent_name"] if l2_node else ""
            l1_code = l1_by_name[l1_name]["code"] if l1_name in l1_by_name else ""
            l2_code = l2_node["code"] if l2_node else ""

            # 扁平记录：搜索与成分股 API 需要完整上下级上下文
            node = {
                "code": code,
                "name": name,
                "count": count,
                "l1_code": l1_code,
                "l1_name": l1_name,
                "l2_code": l2_code,
                "l2_name": parent_name,
            }
            flat_l3.append(node)
            # 树节点上的三级只保留展示所需的精简字段
            if l2_node is not None:
                l2_node["children"].append(
                    {
                        "code": code,
                        "name": name,
                        "count": count,
                    }
                )

        # 清理组装期临时字段，避免暴露给前端
        for l1 in l1_list:
            for l2 in l1["children"]:
                l2.pop("parent_name", None)

        # 持久化：树 + 扁平三级，便于下次冷启动直接读盘
        payload = {
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "tree": l1_list,
            "flat_l3": flat_l3,
        }
        TREE_CACHE.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._tree = l1_list
        self._flat_l3 = {item["code"]: item for item in flat_l3}
        return l1_list

    def get_l3_meta(self, code: str) -> dict[str, Any] | None:
        """按三级行业代码取元数据；找不到返回 None。

        会先确保行业树已加载（副作用：可能触发磁盘/远程加载）。
        """
        self.get_tree()
        return self._flat_l3.get(code)

    def search(self, keyword: str) -> list[dict[str, Any]]:
        """在三级行业扁平表中做子串搜索。

        匹配范围：三级名、一级名、二级名、行业代码（大小写不敏感）。
        结果按一级名 → 二级名 → 三级名排序，最多返回 80 条。

        对应 API：GET /api/search?q=
        """
        self.get_tree()
        kw = keyword.strip().lower()
        if not kw:
            return []
        results = []
        for item in self._flat_l3.values():
            # 拼成单一字符串做 contains，简单够用
            hay = f"{item['name']}{item['l1_name']}{item['l2_name']}{item['code']}".lower()
            if kw in hay:
                results.append(item)
        results.sort(key=lambda x: (x["l1_name"], x["l2_name"], x["name"]))
        return results[:80]

    # -----------------------------------------------------------------------
    # 成分股
    # -----------------------------------------------------------------------

    def get_constituents(
        self, code: str, force_refresh: bool = False, update_index: bool = True
    ) -> dict[str, Any]:
        """获取指定三级行业的成分股列表。

        流程：
        1. 校验三级行业存在；
        2. 若磁盘缓存未过期且非强制刷新 → 直接返回；
        3. 否则经 cons_fetcher 拉取远端，规范化字段后写缓存；
        4. 可选：将本次股票合并进全局索引（全量构建时会关掉以免频繁写盘）。

        Args:
            code: 三级行业代码，如 "850111.SI"
            force_refresh: 忽略 TTL，强制重新拉取
            update_index: 是否把结果合并进 _stock_index 并落盘

        Returns:
            {
              industry,   # 三级行业元数据
              count,      # 股票数
              stocks,     # 股票列表
              fetched_at, # Unix 时间戳，用于 TTL 判断
              updated_at, # 可读时间字符串
            }

        Raises:
            KeyError: 行业代码不在 flat_l3 中
        """
        code = code.strip()
        meta = self.get_l3_meta(code)
        if meta is None:
            raise KeyError(f"未找到三级行业: {code}")

        # Windows 友好：文件名不能含 '.'，统一替换为 '_'
        cache_file = CONS_CACHE_DIR / f"{code.replace('.', '_')}.json"

        # 有效期内的缓存：可直接返回，并按需刷新索引中的该批股票
        if cache_file.exists() and not force_refresh:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            if time.time() - cached.get("fetched_at", 0) < CONS_TTL:
                if update_index:
                    self._merge_stocks_into_index(meta, cached.get("stocks") or [])
                return cached

        # 远程拉取（legulegu HTML 表格）
        df = fetch_third_cons(code)

        def _cell(row: Any, key: str) -> str:
            val = row.get(key, "")
            if val is None or (isinstance(val, float) and pd.isna(val)):
                return ""
            text = str(val).strip()
            return "" if text in {"nan", "None", "—", "-", "<NA>"} else text

        stocks = []
        for _, row in df.iterrows():
            stock_code = _cell(row, "股票代码")
            # 短代码：去掉交易所后缀，如 "000001.SZ" → "000001"
            short_code = stock_code.split(".")[0] if stock_code else ""
            stocks.append(
                {
                    "code": short_code,
                    "full_code": stock_code,
                    "name": _cell(row, "股票简称"),
                    "l1": meta.get("l1_name", ""),
                    "l2": meta.get("l2_name", ""),
                    # 表格里的申万3级优先，缺失时回退到行业树中的名称
                    "l3": _cell(row, "申万3级") or meta.get("name", ""),
                    "include_date": _cell(row, "纳入时间"),
                    # 乐咕乐股表行情 / 估值 / 涨幅等（跳过细分概念列）
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
            )

        payload = {
            "industry": meta,
            "count": len(stocks),
            "stocks": stocks,
            "fetched_at": time.time(),  # TTL 依据
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        cache_file.write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )
        if update_index:
            self._merge_stocks_into_index(meta, stocks)
        return payload

    # -----------------------------------------------------------------------
    # 全局股票索引（加载 / 重建 / 合并 / 持久化）
    # -----------------------------------------------------------------------

    def _load_stock_index_from_disk(self) -> None:
        """启动时从磁盘恢复全局股票索引。

        若 stocks_index.json 不存在，则尝试扫描已有 cons/*.json 拼出一份
        不完整但可用的索引，避免搜索完全空白。
        """
        if not STOCK_INDEX_CACHE.exists():
            # 尝试从已有成分股缓存拼出索引
            self._rebuild_index_from_cons_cache()
            return
        try:
            data = json.loads(STOCK_INDEX_CACHE.read_text(encoding="utf-8"))
            self._stock_index = data.get("stocks", [])
            self._index_ready = len(self._stock_index) > 0
        except Exception:  # noqa: BLE001
            # 文件损坏时降级为空索引，后续可由 start_build_stock_index 重建
            self._stock_index = []
            self._index_ready = False

    def _rebuild_index_from_cons_cache(self) -> None:
        """扫描 cons/ 下全部成分股缓存，去重后拼出全局索引。

        用于：stocks_index.json 缺失，或 search_stocks 发现内存索引为空。
        同一股票若出现在多个缓存中，以先扫到的为准（seen 集合去重）。
        """
        stocks: list[dict[str, Any]] = []
        seen: set[str] = set()
        for path in CONS_CACHE_DIR.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue  # 跳过坏文件，不影响其余缓存
            industry = payload.get("industry") or {}
            for s in payload.get("stocks") or []:
                key = s.get("full_code") or s.get("code")
                if not key or key in seen:
                    continue
                seen.add(key)
                stocks.append(
                    {
                        "code": s.get("code", ""),
                        "full_code": s.get("full_code", ""),
                        "name": s.get("name", ""),
                        "include_date": s.get("include_date", ""),
                        # 行业归属优先取缓存里的 industry 元数据
                        "l1_name": industry.get("l1_name") or s.get("l1", ""),
                        "l2_name": industry.get("l2_name") or s.get("l2", ""),
                        "l3_name": industry.get("name") or s.get("l3", ""),
                        "l3_code": industry.get("code", ""),
                    }
                )
        self._stock_index = stocks
        self._index_ready = len(stocks) > 0
        if stocks:
            self._save_stock_index()

    def _save_stock_index(self) -> None:
        """将当前内存中的全局股票索引写入 stocks_index.json。"""
        payload = {
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "count": len(self._stock_index),
            "stocks": self._stock_index,
        }
        STOCK_INDEX_CACHE.write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )

    def _merge_stocks_into_index(
        self, meta: dict[str, Any], stocks: list[dict[str, Any]]
    ) -> None:
        """把某一行业的成分股增量合并进全局索引并立即落盘。

        以 full_code（或 code）为键：已存在则覆盖更新行业归属，不存在则新增。
        适合「用户点开某个行业」时渐进丰富索引；全量构建时通常关闭此路径。
        """
        by_key = {
            (s.get("full_code") or s.get("code")): s for s in self._stock_index
        }
        for s in stocks:
            key = s.get("full_code") or s.get("code")
            if not key:
                continue
            by_key[key] = {
                "code": s.get("code", ""),
                "full_code": s.get("full_code", ""),
                "name": s.get("name", ""),
                "include_date": s.get("include_date", ""),
                "l1_name": meta.get("l1_name", ""),
                "l2_name": meta.get("l2_name", ""),
                "l3_name": meta.get("name", ""),
                "l3_code": meta.get("code", ""),
            }
        self._stock_index = list(by_key.values())
        self._index_ready = True
        self._save_stock_index()

    def get_index_status(self) -> dict[str, Any]:
        """返回股票索引构建状态，供前端轮询。

        对应 API：GET /api/stocks/index/status
        """
        return {
            "ready": self._index_ready,
            "building": self._index_building,
            "count": len(self._stock_index),
            "progress": dict(self._index_progress),  # 拷贝，避免外部误改内部状态
            "error": self._index_error,
        }

    def start_build_stock_index(self, force: bool = False) -> dict[str, Any]:
        """异步全量构建全局股票索引。

        行为：
        - 若已在构建中 → 直接返回当前状态，不重复开线程；
        - 若索引已 ready、非 force、且股票数 > 1000 → 视为足够完整，跳过；
        - 否则启动 daemon 线程：遍历全部三级行业，读缓存或拉远端成分股，
          去重汇总后一次性写盘。构建过程中 update_index=False，避免每行业写盘。

        对应 API：POST /api/stocks/index/rebuild?force=1
        启动时 app.py 也会调用一次做预热。
        """
        if self._index_building:
            return self.get_index_status()
        # 已有较完整索引且非强制重建时，跳过全量任务
        if self._index_ready and not force and len(self._stock_index) > 1000:
            return self.get_index_status()

        def worker() -> None:
            """后台 worker：遍历全部 L3，汇总成分股为全局索引。"""
            self._index_building = True
            self._index_error = ""
            try:
                self.get_tree()
                codes = list(self._flat_l3.keys())
                self._index_progress = {"done": 0, "total": len(codes)}
                collected: list[dict[str, Any]] = []
                seen: set[str] = set()
                for code in codes:
                    try:
                        # 优先吃磁盘缓存；不在此处 merge 索引，最后统一赋值
                        data = self.get_constituents(
                            code, force_refresh=False, update_index=False
                        )
                        meta = data.get("industry") or self._flat_l3.get(code) or {}
                        for s in data.get("stocks") or []:
                            key = s.get("full_code") or s.get("code")
                            if not key or key in seen:
                                continue
                            seen.add(key)
                            collected.append(
                                {
                                    "code": s.get("code", ""),
                                    "full_code": s.get("full_code", ""),
                                    "name": s.get("name", ""),
                                    "include_date": s.get("include_date", ""),
                                    "l1_name": meta.get("l1_name", ""),
                                    "l2_name": meta.get("l2_name", ""),
                                    "l3_name": meta.get("name", ""),
                                    "l3_code": meta.get("code", code),
                                }
                            )
                    except Exception:  # noqa: BLE001
                        # 单个行业失败不中断全量任务（网络抖动等）
                        pass
                    self._index_progress["done"] += 1
                # 全量替换内存索引并落盘
                self._stock_index = collected
                self._index_ready = True
                self._save_stock_index()
            except Exception as exc:  # noqa: BLE001
                self._index_error = str(exc)
            finally:
                self._index_building = False

        # daemon=True：主进程退出时不阻塞；适合开发态 Flask debug
        threading.Thread(target=worker, daemon=True).start()
        return self.get_index_status()

    # -----------------------------------------------------------------------
    # 股票搜索
    # -----------------------------------------------------------------------

    def search_stocks(
        self, name: str = "", code: str = "", limit: int = 80
    ) -> list[dict[str, Any]]:
        """按股票名称和/或代码在全局索引中检索。

        - name / code 均为空 → 返回 []
        - 内存索引为空时，先尝试从 cons 缓存拼一份
        - 索引条数 < 1000 且未在构建中 → 自动触发后台全量补全
          （本次搜索仍基于当前已有数据，后续请求会更全）

        对应 API：GET /api/stocks/search?name=&code=
        """
        name_kw = name.strip().lower()
        code_kw = code.strip().lower()
        if not name_kw and not code_kw:
            return []

        if not self._stock_index:
            self._rebuild_index_from_cons_cache()

        # 索引过少时自动后台补全，便于全局搜索
        if not self._index_building and len(self._stock_index) < 1000:
            self.start_build_stock_index(force=False)

        results = []
        for item in self._stock_index:
            # 名称：子串包含（不区分大小写）
            if name_kw and name_kw not in str(item.get("name", "")).lower():
                continue
            # 代码：同时匹配短码与完整码
            code_hay = f"{item.get('code', '')}{item.get('full_code', '')}".lower()
            if code_kw and code_kw not in code_hay:
                continue
            results.append(item)
            if len(results) >= limit:
                break
        return results


    def get_stock_profile(
        self, code: str, industry_code: str = "", name: str = ""
    ) -> dict[str, Any]:
        """Resolve a stock's metrics + industry meta for the company detail page."""
        code = (code or "").strip()
        if not code:
            raise ValueError("缺少公司代码")

        industry_code = (industry_code or "").strip()
        name = (name or "").strip()
        index_hit: dict[str, Any] | None = None

        if not self._stock_index:
            self._rebuild_index_from_cons_cache()

        code_l = code.lower()
        for item in self._stock_index:
            hay = f"{item.get('code', '')}{item.get('full_code', '')}".lower()
            if code_l == str(item.get("code", "")).lower() or code_l in hay:
                index_hit = item
                break

        if not industry_code and index_hit:
            industry_code = str(index_hit.get("l3_code") or "").strip()

        industry_meta = self.get_l3_meta(industry_code) if industry_code else None
        stock: dict[str, Any] | None = None

        if industry_code:
            try:
                data = self.get_constituents(industry_code, force_refresh=False)
            except KeyError:
                data = None
            if data:
                for s in data.get("stocks") or []:
                    if (
                        str(s.get("code", "")).lower() == code_l
                        or str(s.get("full_code", "")).lower() == code_l
                        or code_l in str(s.get("full_code", "")).lower()
                    ):
                        stock = dict(s)
                        break
                if industry_meta is None:
                    industry_meta = data.get("industry")

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

        if stock is None:
            stock = {
                "code": code,
                "full_code": "",
                "name": name or code,
            }

        if industry_meta is None and index_hit:
            industry_meta = {
                "code": index_hit.get("l3_code") or "",
                "name": index_hit.get("l3_name") or "",
                "l1_name": index_hit.get("l1_name") or "",
                "l2_name": index_hit.get("l2_name") or "",
            }

        return {
            "stock": stock,
            "industry": industry_meta or {},
        }


# 进程内单例：Flask 路由与启动预热均 import 此对象
service = IndustryService()
