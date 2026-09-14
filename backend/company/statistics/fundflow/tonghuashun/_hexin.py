"""同花顺 data.10jqka.com.cn 请求签名（hexin-v）。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import py_mini_racer


@lru_cache(maxsize=1)
def _ths_js_source() -> str:
    from akshare.datasets import get_ths_js

    return Path(get_ths_js("ths.js")).read_text(encoding="utf-8")


def make_hexin_v() -> str:
    """生成单次请求可用的 ``hexin-v`` 头（每次调用需重新生成）。"""
    ctx = py_mini_racer.MiniRacer()
    ctx.eval(_ths_js_source())
    return str(ctx.call("v"))
