"""股票宇宙过滤：排除创业板、科创板、ST、退市。"""

from __future__ import annotations

from typing import Any

# 创业板：深市 300 / 301；科创板：沪市 688 / 689
_CHINEXT_PREFIXES = ("300", "301")
_STAR_PREFIXES = ("688", "689")


def _bare6(code: str) -> str:
    text = str(code or "").strip().upper()
    # 兼容 300750 / sz.300001 / 300001.SZ
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits[-6:] if len(digits) >= 6 else digits


def is_chinext(code: str) -> bool:
    """是否创业板（代码 300/301 开头）。"""
    bare = _bare6(code)
    return bare.startswith(_CHINEXT_PREFIXES)


def is_star(code: str) -> bool:
    """是否科创板（代码 688/689 开头）。"""
    bare = _bare6(code)
    return bare.startswith(_STAR_PREFIXES)


def is_st(name: str) -> bool:
    """名称是否含 ST（含 *ST / S*ST 等）。"""
    return "ST" in str(name or "").upper()


def is_delisted(name: str) -> bool:
    """名称是否含退市标记（退市 / 退）。"""
    text = str(name or "")
    if "退市" in text:
        return True
    # 单字「退」常见于退市整理简称；避免误伤需同时排除纯 ST 已由 is_st 处理
    return "退" in text


def is_eligible_stock(meta: dict[str, Any] | None) -> bool:
    """筛选宇宙：排除创业板、科创板、ST、退市。"""
    if not meta:
        return False
    code = str(meta.get("code") or "").strip()
    if not code or is_chinext(code) or is_star(code):
        return False
    name = str(meta.get("name") or "")
    if is_st(name) or is_delisted(name):
        return False
    return True
