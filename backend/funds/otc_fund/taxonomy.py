"""场外开放式基金分类（东财排行 ``ft`` 参数）。"""

from __future__ import annotations

from typing import Any

CATEGORY_META: dict[str, dict[str, str]] = {
    "all": {"name": "全部开放式", "ft": "all"},
    "gp": {"name": "股票型", "ft": "gp"},
    "hh": {"name": "混合型", "ft": "hh"},
    "zq": {"name": "债券型", "ft": "zq"},
    "zs": {"name": "指数型", "ft": "zs"},
    "qdii": {"name": "QDII", "ft": "qdii"},
    "fof": {"name": "FOF", "ft": "fof"},
    "hb": {"name": "货币型", "ft": "hb"},
}

GROUP_META: dict[str, str] = {
    "open": "开放式基金",
}

ALL_CATEGORY_CODES: tuple[str, ...] = tuple(CATEGORY_META.keys())


def get_category(code: str) -> dict[str, str] | None:
    meta = CATEGORY_META.get(code.strip())
    if meta is None:
        return None
    return {"code": code.strip(), **meta}


def build_tree(counts: dict[str, int] | None = None) -> list[dict[str, Any]]:
    counts = counts or {}
    children = []
    for code, meta in CATEGORY_META.items():
        children.append(
            {
                "code": code,
                "name": meta["name"],
                "count": int(counts.get(code, 0)),
                "ft": meta["ft"],
            }
        )
    return [
        {
            "code": "open",
            "name": GROUP_META["open"],
            "count": sum(int(counts.get(code, 0)) for code in ALL_CATEGORY_CODES),
            "children": children,
        }
    ]


def flat_categories() -> list[dict[str, Any]]:
    return [{"code": code, **meta} for code, meta in CATEGORY_META.items()]
