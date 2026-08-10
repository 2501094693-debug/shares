"""七家指定披露媒体统一查询入口。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Literal

from message.disclosure.http_util import (
    dedupe,
    default_start,
    sort_key,
)

from .constants import OUTLET_BY_ID, OUTLETS, Outlet
from .eastmoney import fetch_all_outlets_via_eastmoney, fetch_outlet_via_eastmoney
from .resolve import resolve_keywords
from .sites import fetch_outlet_direct

OutletId = Literal[
    "cs",
    "cnstock",
    "stcn",
    "zqrb",
    "financialnews",
    "jjckb",
    "chinadaily",
    "all",
]


def _select_outlets(outlet: str | Iterable[str] | None) -> list[Outlet]:
    if outlet is None or outlet == "all":
        return list(OUTLETS)
    if isinstance(outlet, str):
        ids = [x.strip() for x in outlet.split(",") if x.strip()]
    else:
        ids = [str(x).strip() for x in outlet if str(x).strip()]
    if not ids or ids == ["all"]:
        return list(OUTLETS)
    selected: list[Outlet] = []
    for oid in ids:
        if oid not in OUTLET_BY_ID:
            raise ValueError(
                f"未知媒体 id: {oid}；可选: {', '.join(OUTLET_BY_ID)}"
            )
        selected.append(OUTLET_BY_ID[oid])
    return selected


def query_press(
    code_or_name: str,
    *,
    outlet: str | Iterable[str] | None = "all",
    start: datetime | None = None,
    end: datetime | None = None,
    days: int | None = 365,
    max_pages: int = 5,
    include_direct: bool = True,
) -> dict[str, Any]:
    """查询指定公司在七家指定披露媒体上的相关消息。

    Parameters
    ----------
    code_or_name:
        股票代码或公司简称，如 ``600519`` / ``贵州茅台``。
    outlet:
        ``all`` 或媒体 id（可用逗号组合）：
        cs / cnstock / stcn / zqrb / financialnews / jjckb / chinadaily
    """
    resolved = resolve_keywords(code_or_name)
    code = resolved["code"]
    name = resolved["name"]
    keyword = resolved["keyword"]
    if not keyword:
        return {
            "code": code,
            "name": name,
            "keyword": keyword,
            "outlets": {},
            "items": [],
            "count": 0,
        }

    if start is None and days is not None:
        start = default_start(days)

    outlets = _select_outlets(outlet)
    by_outlet = fetch_all_outlets_via_eastmoney(
        keyword,
        outlets=outlets,
        start=start,
        end=end,
        max_pages=max_pages,
        code=code,
        name=name,
    )

    if include_direct:
        for o in outlets:
            extra = fetch_outlet_direct(
                keyword,
                o,
                start=start,
                end=end,
                code=code,
                name=name,
            )
            if extra:
                merged = dedupe((by_outlet.get(o["id"]) or []) + extra)
                by_outlet[o["id"]] = sorted(merged, key=sort_key)

    # 各通道内部再排序
    for oid, rows in list(by_outlet.items()):
        by_outlet[oid] = sorted(dedupe(rows), key=sort_key)

    flat: list[dict[str, Any]] = []
    for rows in by_outlet.values():
        flat.extend(rows)
    flat = sorted(dedupe(flat), key=sort_key)

    return {
        "code": code,
        "name": name,
        "keyword": keyword,
        "outlets": by_outlet,
        "counts": {oid: len(rows) for oid, rows in by_outlet.items()},
        "items": flat,
        "count": len(flat),
    }


def query_press_flat(
    code_or_name: str,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """只返回合并去重后的列表。"""
    return list(query_press(code_or_name, **kwargs).get("items") or [])
