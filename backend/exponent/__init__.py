"""A 股指数模块（东财 / 同花顺双数据源）。

- ``exponent.eastmoney``：东财 push2，无需登录
- ``exponent.tonghuashun``：官方 thsdk，需扫码登录

顶层保留 ``api`` / CLI；默认数据源为东财。
"""

from __future__ import annotations

from typing import Any


def _pkg(source: str = "eastmoney") -> Any:
    key = (source or "eastmoney").strip().lower()
    if key in ("eastmoney", "em", "east", "dc"):
        import exponent.eastmoney as pkg

        return pkg
    if key in ("tonghuashun", "ths", "th"):
        import exponent.tonghuashun as pkg

        return pkg
    raise ValueError(f"source 须为 eastmoney|tonghuashun，收到 {source!r}")


def catalog(source: str = "eastmoney"):
    return _pkg(source).catalog()


def fetch_quotes(codes=None, *, source: str = "eastmoney", **kwargs):
    return _pkg(source).fetch_quotes(codes, **kwargs)


def fetch_kline(code: str, *, source: str = "eastmoney", **kwargs):
    return _pkg(source).fetch_kline(code, **kwargs)


def list_indices(markets=None, *, source: str = "eastmoney", **kwargs):
    return _pkg(source).list_indices(markets, **kwargs)


def search_indices(keyword: str, *, source: str = "eastmoney", **kwargs):
    return _pkg(source).search_indices(keyword, **kwargs)


def get_service(source: str = "eastmoney"):
    return _pkg(source).service


__all__ = [
    "catalog",
    "fetch_quotes",
    "fetch_kline",
    "list_indices",
    "search_indices",
    "get_service",
]
