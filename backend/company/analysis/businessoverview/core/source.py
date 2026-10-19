"""数据源统一适配器。

目前只接入 **同花顺 F10 经营分析** 一个数据源。保留 :class:`Source` 抽象是为了
让 ``core.engine`` 保持与数据源无关：将来若再接入新源，只需在这里登记一个
插件，引擎无需改动。

``Source`` 本身不含任何网络逻辑，只是对已有 fetcher 的登记。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from company.analysis.businessoverview.core.normalize import (
    DIM_BY_LABEL,
    canonical_dim_key,
)


@dataclass(frozen=True)
class Source:
    """一个数据源的统一描述。"""

    key: str
    label: str
    page_url: str
    api: str
    dim_labels: dict
    dim_priority: tuple
    normalize_dim: Callable
    fetch_segments: Callable
    fetch_all: Callable
    fetch_periods: Callable
    meta: dict = field(default_factory=dict)

    def normalize(self, value):
        """归一维度别名到**全局统一键**（product/industry/area）。

        统一键为 product/industry/area，源内键与中文标签均归一到该组键。
        无法识别返回 ``''``。
        """
        try:
            key = self.normalize_dim(value)
        except Exception:
            return ""
        return canonical_dim_key(key)

    def dim_label(self, key):
        return self.dim_labels.get(key, "")

    def page(self, code):
        try:
            return self.page_url.format(code=code)
        except (KeyError, IndexError):
            return self.page_url

    def segments(self, code, latest_n=1, dimension="", date=""):
        """拉主营构成。``date`` 非空时按指定报告期取。"""
        return self.fetch_segments(
            code, latest_n=latest_n, dimension=dimension, date=date
        )

    def fetch(self, code, latest_n=1, dimension=""):
        return self.fetch_all(code, latest_n=latest_n, analysis_type=dimension)

    def periods(self, code):
        return self.fetch_periods(code)


_ALIASES = {
    "同花顺": "tonghuashun",
    "ths": "tonghuashun",
    "tonghuashun": "tonghuashun",
}

# 全局统一维度词表
CANONICAL_DIMS = dict(DIM_BY_LABEL)


def canonical_dim(dim_key: str, dim_labels: dict) -> str:
    """源内维度键 → 全局统一维度键；无法识别返回 ``''``。"""
    return canonical_dim_key(dim_key)


def _load_sources():
    """延迟导入数据源，避免包初始化时的循环依赖。"""
    from company.analysis.businessoverview.tonghuashun import SOURCE as THS

    return {THS.key: THS}


def get_source(key=""):
    """按 key 取数据源；留空返回唯一数据源（同花顺）。"""
    sources = _load_sources()
    if not key:
        return sources["tonghuashun"]
    k = str(key).strip().lower()
    k = _ALIASES.get(k, k)
    if k not in sources:
        raise ValueError(f"source 须为 {' | '.join(sources)}")
    return sources[k]


def list_sources():
    """已接入的数据源列表。"""
    sources = _load_sources()
    return [sources["tonghuashun"]]


__all__ = ["Source", "get_source", "list_sources", "canonical_dim", "CANONICAL_DIMS"]
