"""指数代码解析：公开 6 位码 / 东财 secid / 名称 → 规范条目。"""

from __future__ import annotations

import re
from typing import Any

from exponent.eastmoney.catalog import by_code

_SECID_RE = re.compile(r"^\d+\.[0-9A-Za-z]+$")
_PREFIX_RE = re.compile(r"^(SH|SZ|BJ|CSI)(\d{6})$", re.I)
_SUFFIX_RE = re.compile(r"^(\d{6})\.(SH|SZ|BJ|CSI)$", re.I)
_PREFIX_MARKET = {"SH": "1", "SZ": "0", "BJ": "0", "CSI": "2"}


def normalize_display_code(raw: str) -> str:
    text = (raw or "").strip().upper()
    if not text or _SECID_RE.match(text):
        return ""
    text = re.sub(r"^(SH|SZ|BJ|CSI)", "", text)
    text = text.replace(".SH", "").replace(".SZ", "").replace(".BJ", "").replace(".CSI", "")
    digits = re.sub(r"[^0-9]", "", text)
    if digits:
        return digits.zfill(6) if len(digits) <= 6 else digits
    return ""


def _guess_secid(code: str) -> str:
    """无目录命中时的粗分：深证 399/15x、北证 8/4/899、中证 932xxx → 2，其余上证 1。"""
    c = code.zfill(6) if code.isdigit() and len(code) <= 6 else code
    if c.startswith(("399", "15")):
        return f"0.{c}"
    if c.startswith(("8", "4")) or c.startswith("899"):
        return f"0.{c}"
    if c.startswith("932") or (len(c) == 6 and c[0] == "9" and not c.startswith("899")):
        return f"2.{c}"
    return f"1.{c}"


def resolve(code_or_secid: str) -> dict[str, Any]:
    """解析为 ``{code, name, secid, ...}``。优先本地目录。"""
    raw = (code_or_secid or "").strip()
    if not raw:
        raise ValueError("空指数代码")

    catalog_map = by_code()
    upper = raw.upper().replace(" ", "")

    display = normalize_display_code(raw)
    if display and display in catalog_map:
        return dict(catalog_map[display])

    if _SECID_RE.match(raw):
        for item in catalog_map.values():
            if item["secid"] == raw:
                return dict(item)
        code = raw.split(".", 1)[1]
        if code.isdigit() and len(code) <= 6:
            code = code.zfill(6)
        return {"code": code, "name": "", "secid": raw}

    prefixed = _PREFIX_RE.match(upper)
    if prefixed:
        mid = _PREFIX_MARKET[prefixed.group(1).upper()]
        code = prefixed.group(2)
        secid = f"{mid}.{code}"
        if code in catalog_map and catalog_map[code]["secid"] == secid:
            return dict(catalog_map[code])
        return {"code": code, "name": "", "secid": secid}

    suffixed = _SUFFIX_RE.match(upper)
    if suffixed:
        code = suffixed.group(1)
        mid = _PREFIX_MARKET[suffixed.group(2).upper()]
        secid = f"{mid}.{code}"
        if code in catalog_map:
            return dict(catalog_map[code])
        return {"code": code, "name": "", "secid": secid}

    if display:
        return {
            "code": display,
            "name": "",
            "secid": _guess_secid(display),
        }

    raise ValueError(f"未识别指数代码: {raw}")
