"""行情 HTTP 客户端。

行情接口用标准 requests，且 ``trust_env=False`` 关闭代理：东财 push2 / 腾讯
在 Windows 代理或 curl_cffi 干扰下经常被掐。公告/新闻站点请用 ``browser_get`` /
``browser_post``（优先 curl_cffi Chrome 指纹）。

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


def browser_get(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 20,
):
    """GET：优先 curl_cffi（Chrome 指纹），否则退回普通 requests。

    东财 F10 等页面会嗅探 UA；行情接口请继续用 ``get_json`` / ``get_text``
    （``trust_env=False``，避免系统代理把 push2 / 腾讯掐掉）。
    """
    try:
        from curl_cffi import requests as curl_requests
    except ImportError:  # pragma: no cover
        curl_requests = None

    hdrs = {"User-Agent": _UA, **(headers or {})}
    if curl_requests is not None:
        return curl_requests.get(
            url,
            params=params,
            headers=hdrs,
            timeout=timeout,
            impersonate="chrome",
        )
    sess = _session()
    return sess.get(url, params=params, headers=hdrs, timeout=timeout)


def browser_post(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    data: Any = None,
    json_body: Any = None,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
):
    """POST：优先 curl_cffi（Chrome 指纹），否则退回普通 requests。

    巨潮 ``hisAnnouncement/query`` 等站点会校验 Origin / Referer；
    行情接口请继续用 ``get_json``（``trust_env=False``）。
    """
    try:
        from curl_cffi import requests as curl_requests
    except ImportError:  # pragma: no cover
        curl_requests = None

    hdrs = {"User-Agent": _UA, **(headers or {})}
    if curl_requests is not None:
        return curl_requests.post(
            url,
            params=params,
            data=data,
            json=json_body,
            headers=hdrs,
            timeout=timeout,
            impersonate="chrome",
        )
    sess = _session()
    return sess.post(
        url,
        params=params,
        data=data,
        json=json_body,
        headers=hdrs,
        timeout=timeout,
    )


def get_bytes(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 60,
) -> bytes:
    """GET 返回原始字节（公告 PDF 等）。优先 curl_cffi。"""
    resp = browser_get(url, params=params, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.content
