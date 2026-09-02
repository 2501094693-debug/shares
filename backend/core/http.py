"""行情 HTTP 客户端。

行情接口用标准 requests，且 ``trust_env=False`` 关闭代理：东财 push2 / 腾讯
在 Windows 代理或 curl_cffi 干扰下经常被掐。公告/新闻站点请用 ``browser_get`` /
``browser_post``（优先 curl_cffi Chrome 指纹）。

每次请求新建 Session，避免跨线程复用同一 Session 的状态问题。
超时 / 断连默认再试一次，避免申万、东财盘中偶发 Read timed out 直接失败。
"""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlparse, urlunparse

import requests
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager

from core.resolve import remember_host, resolve_ipv4

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)
_RETRY_EXC = (requests.Timeout, requests.ConnectionError)


def _session(*, verify: bool = True) -> requests.Session:
    sess = requests.Session()
    sess.trust_env = False
    sess.verify = verify
    sess.headers.update({"User-Agent": _UA})
    return sess


def _is_dns_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    if "failed to resolve" in text or "getaddrinfo" in text or "nameresolution" in text:
        return True
    cause = getattr(exc, "__cause__", None)
    if cause is not None and cause is not exc:
        return _is_dns_error(cause)
    return False


class _SNIAdapter(HTTPAdapter):
    """按 IP 建连，SNI 仍用原域名（东财 CDN 校验 Host）。"""

    def __init__(self, server_hostname: str, **kwargs: Any) -> None:
        self._sni = server_hostname
        super().__init__(**kwargs)

    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        pool_kwargs["server_hostname"] = self._sni
        self.poolmanager = PoolManager(
            num_pools=connections, maxsize=maxsize, block=block, **pool_kwargs
        )


def _url_with_ip(url: str, ip: str) -> str:
    parsed = urlparse(url)
    netloc = ip if not parsed.port else f"{ip}:{parsed.port}"
    return urlunparse(parsed._replace(netloc=netloc))


def _get_via_ip(
    url: str,
    *,
    params: dict[str, Any] | None,
    headers: dict[str, str] | None,
    timeout: int | tuple[float, float],
) -> requests.Response:
    host = (urlparse(url).hostname or "").strip()
    ips = resolve_ipv4(host)
    if not ips:
        raise requests.ConnectionError(f"无法解析 {host}")
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    last_error: Exception | None = None
    for ip in ips:
        try:
            sess = _session(verify=False)
            sess.mount("https://", _SNIAdapter(host))
            hdrs = {"User-Agent": _UA, **(headers or {}), "Host": host}
            resp = sess.get(
                _url_with_ip(url, ip), params=params, headers=hdrs, timeout=timeout
            )
            resp.raise_for_status()
            return resp
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    raise last_error or requests.ConnectionError(f"无法连接 {host}")


def _get(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int | tuple[float, float] = 12,
    retries: int = 1,
    verify: bool = True,
) -> requests.Response:
    """GET；超时重试；DNS 11001 改走 DoH 解析后的 IP。"""
    if not verify:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    last_error: Exception | None = None
    attempts = max(1, int(retries) + 1)
    host = urlparse(url).hostname or ""
    for attempt in range(attempts):
        try:
            sess = _session(verify=verify)
            resp = sess.get(
                url, params=params, headers=headers or {}, timeout=timeout
            )
            resp.raise_for_status()
            remember_host(host)
            return resp
        except _RETRY_EXC as exc:
            last_error = exc
            if _is_dns_error(exc):
                return _get_via_ip(
                    url, params=params, headers=headers, timeout=timeout
                )
            if attempt >= attempts - 1:
                raise
            time.sleep(0.4 * (attempt + 1))
    raise last_error  # pragma: no cover


def get_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int | tuple[float, float] = 12,
    retries: int = 1,
    verify: bool = True,
) -> Any:
    """GET 并解析 JSON；HTTP 错误抛 ``requests.HTTPError``。"""
    resp = _get(
        url,
        params=params,
        headers=headers,
        timeout=timeout,
        retries=retries,
        verify=verify,
    )
    return resp.json()


def get_text(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int | tuple[float, float] = 12,
    encoding: str | None = None,
    retries: int = 1,
    verify: bool = True,
) -> str:
    """GET 返回文本。``encoding`` 非空时强制解码（腾讯行情页偶发编码错）。"""
    resp = _get(
        url,
        params=params,
        headers=headers,
        timeout=timeout,
        retries=retries,
        verify=verify,
    )
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
