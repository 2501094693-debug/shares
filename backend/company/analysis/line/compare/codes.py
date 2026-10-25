"""可选对比指数目录（宽基）。

公开码与 ``exponent.eastmoney.catalog`` 对齐；解析名称 / 6 位码 / SH000300 均可。
"""

from __future__ import annotations

from typing import Any

# 用户指定可对比的五只指数
COMPARE_INDICES: tuple[dict[str, str], ...] = (
    {"code": "000001", "name": "上证指数"},
    {"code": "399001", "name": "深证成指"},
    {"code": "000300", "name": "沪深300"},
    {"code": "000905", "name": "中证500"},
    {"code": "000852", "name": "中证1000"},
)

# 四项对比口径：相对各自前收
FACTORS: tuple[str, ...] = ("open", "high", "low", "close")
FACTOR_LABELS: dict[str, str] = {
    "open": "开盘涨跌幅",
    "high": "最大涨幅",
    "low": "最大跌幅",
    "close": "收盘涨跌幅",
}

_NAME_ALIASES: dict[str, str] = {
    "上证": "000001",
    "上证指数": "000001",
    "上证综指": "000001",
    "深证": "399001",
    "深成指": "399001",
    "深证成指": "399001",
    "沪深300": "000300",
    "沪深三百": "000300",
    "csi300": "000300",
    "中证500": "000905",
    "中证五百": "000905",
    "csi500": "000905",
    "中证1000": "000852",
    "中证一千": "000852",
    "csi1000": "000852",
}


def catalog() -> list[dict[str, str]]:
    return [dict(item) for item in COMPARE_INDICES]


def _by_code() -> dict[str, dict[str, str]]:
    return {item["code"]: dict(item) for item in COMPARE_INDICES}


def normalize_index_code(raw: str) -> str:
    """名称 / 公开码 / SH000300 / 1.000300 → 6 位公开码。"""
    text = (raw or "").strip()
    if not text:
        raise ValueError("空指数代码")

    alias = _NAME_ALIASES.get(text) or _NAME_ALIASES.get(text.lower())
    if alias:
        return alias

    upper = text.upper().replace(" ", "")
    for prefix in ("SH", "SZ", "BJ", "CSI"):
        if upper.startswith(prefix) and upper[len(prefix) :].isdigit():
            upper = upper[len(prefix) :]
            break
    for suffix in (".SH", ".SZ", ".BJ", ".CSI"):
        if upper.endswith(suffix):
            upper = upper[: -len(suffix)]
            break
    if "." in upper and upper.split(".", 1)[0].isdigit():
        upper = upper.split(".", 1)[1]

    digits = "".join(ch for ch in upper if ch.isdigit())
    if digits:
        code = digits.zfill(6) if len(digits) <= 6 else digits
        known = _by_code()
        if code in known:
            return code
        # 允许目录外指数（仍走 exponent 解析）
        return code

    raise ValueError(f"未识别指数: {raw}")


def resolve_indices(raw: str | list[str] | None) -> list[dict[str, str]]:
    """解析用户选择的指数列表；空则默认五只全部。"""
    known = _by_code()
    if raw is None or raw == "" or raw == []:
        return catalog()

    if isinstance(raw, str):
        parts = [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]
    else:
        parts = [str(p).strip() for p in raw if str(p).strip()]

    if not parts:
        return catalog()

    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for part in parts:
        code = normalize_index_code(part)
        if code in seen:
            continue
        seen.add(code)
        meta = known.get(code) or {"code": code, "name": ""}
        out.append(dict(meta))
    return out


def factor_meta() -> list[dict[str, Any]]:
    return [{"key": k, "label": FACTOR_LABELS[k]} for k in FACTORS]
