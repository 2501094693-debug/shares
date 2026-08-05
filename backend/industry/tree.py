"""申万行业树：构建、缓存、行业检索。"""

from __future__ import annotations

import json
import threading
import time
from typing import Any

import akshare as ak
import pandas as pd

from core.paths import TREE_CACHE, ensure_cache_dirs

_FETCH_RETRIES = 3
_FETCH_RETRY_SLEEP_SEC = 2.0


def _fetch_sw_frames() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """从乐咕乐股拉取申万一/二/三级表；站点过载时 HTML 无节点会触发 AttributeError。"""
    last_exc: BaseException | None = None
    for attempt in range(1, _FETCH_RETRIES + 1):
        try:
            l1_df = ak.sw_index_first_info()
            l2_df = ak.sw_index_second_info()
            l3_df = ak.sw_index_third_info()
            if l1_df is None or l1_df.empty or l2_df is None or l2_df.empty or l3_df is None or l3_df.empty:
                raise RuntimeError("申万行业接口返回空表")
            return l1_df, l2_df, l3_df
        except AttributeError as exc:
            # soup.find(...)=None 后再 .find_all → 'NoneType' has no attribute 'find_all'
            last_exc = exc
            msg = (
                "乐咕乐股申万行业页暂不可用或页面结构变化"
                "（未找到 level1/2/3Items 节点）"
            )
            if attempt >= _FETCH_RETRIES:
                raise RuntimeError(msg) from exc
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt >= _FETCH_RETRIES:
                raise RuntimeError(f"拉取申万行业分类失败: {exc}") from exc
        time.sleep(_FETCH_RETRY_SLEEP_SEC * attempt)
    raise RuntimeError(f"拉取申万行业分类失败: {last_exc}")


class IndustryTree:
    """一级 → 二级 → 三级行业树 + 扁平三级表。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tree: list[dict[str, Any]] | None = None
        self._flat_l3: dict[str, dict[str, Any]] = {}

    @property
    def flat_l3(self) -> dict[str, dict[str, Any]]:
        return self._flat_l3

    def l3_codes(self) -> list[str]:
        self.get_tree()
        return list(self._flat_l3.keys())

    def get_l3_meta(self, code: str) -> dict[str, Any] | None:
        self.get_tree()
        return self._flat_l3.get(code.strip())

    def get_tree(self, force_refresh: bool = False) -> list[dict[str, Any]]:
        with self._lock:
            if self._tree is not None and not force_refresh:
                return self._tree
            if TREE_CACHE.exists() and not force_refresh:
                data = json.loads(TREE_CACHE.read_text(encoding="utf-8"))
                self._tree = data["tree"]
                self._flat_l3 = {item["code"]: item for item in data["flat_l3"]}
                return self._tree
            return self._build_tree()

    def search(self, keyword: str, limit: int = 80) -> list[dict[str, Any]]:
        """三级行业子串搜索（名称 / 上下级名 / 代码）。"""
        self.get_tree()
        kw = keyword.strip().lower()
        if not kw:
            return []
        results = [
            item
            for item in self._flat_l3.values()
            if kw
            in f"{item['l1_name']}{item['l2_name']}{item['name']}{item['code']}".lower()
        ]
        results.sort(key=lambda x: (x["l1_name"], x["l2_name"], x["name"]))
        return results[:limit]

    def _build_tree(self) -> list[dict[str, Any]]:
        ensure_cache_dirs()
        l1_df, l2_df, l3_df = _fetch_sw_frames()
        for df in (l1_df, l2_df, l3_df):
            df.columns = [str(c).strip() for c in df.columns]

        l1_list: list[dict[str, Any]] = []
        for _, row in l1_df.iterrows():
            count = int(row["成份个数"]) if pd.notna(row.get("成份个数")) else 0
            l1_list.append(
                {
                    "code": str(row["行业代码"]).strip(),
                    "name": str(row["行业名称"]).strip(),
                    "count": count,
                    "children": [],
                }
            )
        l1_by_name = {item["name"]: item for item in l1_list}

        l2_list: list[dict[str, Any]] = []
        for _, row in l2_df.iterrows():
            parent_name = str(row.get("上级行业", "")).strip()
            count = int(row["成份个数"]) if pd.notna(row.get("成份个数")) else 0
            node = {
                "code": str(row["行业代码"]).strip(),
                "name": str(row["行业名称"]).strip(),
                "parent_name": parent_name,
                "count": count,
                "children": [],
            }
            l2_list.append(node)
            parent = l1_by_name.get(parent_name)
            if parent is not None:
                parent["children"].append(node)

        l2_by_name = {item["name"]: item for item in l2_list}
        flat_l3: list[dict[str, Any]] = []

        for _, row in l3_df.iterrows():
            parent_name = str(row.get("上级行业", "")).strip()
            count = int(row["成份个数"]) if pd.notna(row.get("成份个数")) else 0
            l2_node = l2_by_name.get(parent_name)
            l1_name = l2_node["parent_name"] if l2_node else ""
            l1_code = l1_by_name[l1_name]["code"] if l1_name in l1_by_name else ""
            l2_code = l2_node["code"] if l2_node else ""
            code = str(row["行业代码"]).strip()
            name = str(row["行业名称"]).strip()
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
            if l2_node is not None:
                l2_node["children"].append({"code": code, "name": name, "count": count})

        for l1 in l1_list:
            for l2 in l1["children"]:
                l2.pop("parent_name", None)

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
