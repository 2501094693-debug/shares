"""A 股代码规范化，以及各行情源使用的市场标识。

- ``normalize_code`` / ``detect_market`` / ``safe_str``：通用
- 东财 push2 / K 线：``secid``，如 ``1.600519``（沪）/ ``0.000001``（深）
- 东财 F10 公司概况：``em_code``，如 ``SH600519``
- 腾讯行情 / 日 K：``tencent_symbol``，如 ``sh600519``

市场判定：60/68 沪，00/30 深，8/4 北。
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

# 东财 secid 市场号：1=上交所，其它（深 / 北 / 未知）走 0，与原 push2 逻辑一致
_EM_SECID_MARKET = {"sse": "1", "szse": "0", "bse": "0"}

# 东财 F10：SH / SZ / BJ
_EM_F10_PREFIX = {"sse": "SH", "szse": "SZ", "bse": "BJ"}

# 腾讯：sh / sz / bj（小写）
_TENCENT_PREFIX = {"sse": "sh", "szse": "sz", "bse": "bj"}


def safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value != value:  # NaN
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return str(value).strip()


def normalize_code(code: str) -> str:
    code = safe_str(code)
    if not code:
        return ""
    # 允许 600519.SH / sh600519
    code = code.upper().replace("SH", "").replace("SZ", "").replace("BJ", "")
    code = re.sub(r"[^0-9]", "", code)
    return code.zfill(6) if code else ""


def detect_market(code: str) -> str:
    """粗分市场：sse / szse / bse / unknown。"""
    c = normalize_code(code)
    if not c:
        return "unknown"
    if c.startswith(("60", "68", "90")):
        return "sse"
    if c.startswith(("00", "30", "20")):
        return "szse"
    if c.startswith(("8", "4", "92")):
        return "bse"
    return "unknown"


def secid(code: str) -> str:
    """东财 push2 用的 secid，例如 ``1.600519``。无效代码返回空串。"""
    c = normalize_code(code)
    if not c:
        return ""
    market = detect_market(c)
    mid = _EM_SECID_MARKET.get(market, "0")
    return f"{mid}.{c}"


def em_code(code: str) -> str:
    """东财 F10 / HSF10 用的代码，例如 ``SH600519``。无效代码返回空串。"""
    c = normalize_code(code)
    if not c:
        return ""
    market = detect_market(c)
    prefix = _EM_F10_PREFIX.get(market, "SH")
    return f"{prefix}{c}"


def tencent_symbol(code: str) -> str:
    """腾讯行情 / 日 K 用的代码，例如 ``sh600519``。无效代码返回空串。"""
    c = normalize_code(code)
    if not c:
        return ""
    market = detect_market(c)
    prefix = _TENCENT_PREFIX.get(market, "sh")
    return f"{prefix}{c}"
