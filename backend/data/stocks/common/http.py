"""行情 HTTP 客户端。

与 ``message.disclosure.http_util.http_get`` 刻意分开：
那边优先 curl_cffi、并尊重系统代理；东财 push2 / 腾讯在 Windows 代理或
curl_cffi 干扰下经常被掐。这里用标准 requests，且 ``trust_env=False`` 关闭代理。

每次请求新建 Session，避免跨线程复用同一 Session 的状态问题。
"""

from __future__ import annotations

from typing import Any

import requests

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


def _session() -> requests.Session:
    sess = requests.Session()
    sess.trust_env = False
    sess.headers.update({"User-Agent": _UA})
    return sess


def get_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 12,
) -> Any:
    """GET 并解析 JSON；HTTP 错误抛 ``requests.HTTPError``。"""
    sess = _session()
    resp = sess.get(url, params=params, headers=headers or {}, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def get_text(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 12,
    encoding: str | None = None,
) -> str:
    """GET 返回文本。``encoding`` 非空时强制解码（腾讯行情页偶发编码错）。"""
    sess = _session()
    resp = sess.get(url, params=params, headers=headers or {}, timeout=timeout)
    resp.raise_for_status()
    if encoding:
        resp.encoding = encoding
    return resp.text
