"""指数代码解析：公开 6 位码 / 同花顺 security / 名称 → 规范条目。"""

from __future__ import annotations

import re
from typing import Any

from exponent.tonghuashun.catalog import by_code

_SECURITY_RE = re.compile(r"^[A-Z]{4}[0-9A-Z]{4,8}$")


def normalize_display_code(raw: str) -> str:
    """收成 6 位公开代码；已是同花顺 security 则原样返回空串由上层处理。"""
    text = (raw or "").strip().upper()
    if not text:
        return ""
    if _SECURITY_RE.match(text):
        return ""
    text = text.replace(".SH", "").replace(".SZ", "").replace(".BJ", "")
    digits = re.sub(r"[^0-9]", "", text)
    if digits:
        return digits.zfill(6) if len(digits) <= 6 else digits
    return ""


def resolve(code_or_security: str) -> dict[str, Any]:
    """解析为 ``{code, name, security, market, ...}``。

    优先命中本地目录；否则：
    - 已是 ``USHIxxxx`` 形式 → 直接用；
    - 否则走 ``thsdk.search_symbols`` / ``complete_ths_code`` 取首个指数命中。
    """
    raw = (code_or_security or "").strip()
    if not raw:
        raise ValueError("空指数代码")

    upper = raw.upper()
    catalog_map = by_code()

    display = normalize_display_code(raw)
    if display and display in catalog_map:
        return dict(catalog_map[display])

    if _SECURITY_RE.match(upper):
        for item in catalog_map.values():
            if item["security"] == upper:
                return dict(item)
        return {
            "code": upper[4:] if len(upper) > 4 else upper,
            "name": "",
            "security": upper,
            "market": upper[:4],
        }

    # 名称或未知短码：同花顺搜索
    from company.line.tonghuashun import auth as _ths_auth
    import thsdk

    if not _ths_auth.ensure(timeout=3):
        raise RuntimeError("THS_NEED_QRCODE:同花顺需扫码登录，前端打开扫码弹窗后重试")

    frame = thsdk.search_symbols(raw)
    if frame is None or len(frame) == 0:
        raise ValueError(f"未找到指数: {raw}")

    # 优先指数市场
    prefer = ("USHI", "USZI", "UZZI", "USTI")
    rows = frame.to_dict("records")
    picked: dict[str, Any] | None = None
    for row in rows:
        market = str(row.get("market") or "")
        if market in prefer:
            picked = row
            break
    if picked is None:
        picked = rows[0]

    security = str(picked.get("full_code") or "").strip()
    if not security:
        raise ValueError(f"未找到指数: {raw}")
    code_display = str(
        picked.get("code_display") or picked.get("code") or ""
    ).strip()
    if code_display.isdigit():
        code_display = code_display.zfill(6)
    return {
        "code": code_display or security[4:],
        "name": str(picked.get("name") or "").strip(),
        "security": security,
        "market": str(picked.get("market") or security[:4]),
    }
