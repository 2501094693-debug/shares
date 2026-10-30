"""行情 HTTP 客户端。

行情接口用标准 requests，且 ``trust_env=False`` 关闭代理：东财 push2 / 腾讯
在 Windows 代理或 curl_cffi 干扰下经常被掐。公告/新闻站点请用 ``browser_get`` /
``browser_post``（优先 curl_cffi Chrome 指纹）。

每次请求新建 Session，避免跨线程复用同一 Session 的状态问题。
超时 / 断连默认再试一次，避免申万、东财盘中偶发 Read timed out 直接失败。
"""

from __future__ import annotations

import random
import time
from typing import Any
from urllib.parse import urlparse, urlunparse

import requests
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager

from core.resolve import (
    canonical_push2_host,
    dial_ips,
    drop_ip,
    forget_host,
    is_eastmoney_push2_host,
    mark_bad_ip,
    remember_host,
    remember_ip,
)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)
_RETRY_EXC = (
    requests.Timeout,
    requests.ConnectionError,
    requests.exceptions.ChunkedEncodingError,
    urllib3.exceptions.ProtocolError,
)
# 对端掐连接时额外多试几次：行情源（东财 / 同花顺 / 腾讯）盘中偶发 10054
_CONN_RESET_EXTRA = 2
_RESET_MARKERS = (
    "connection aborted",
    "connection reset",
    "connectionreseterror",
    "connection reset by peer",
    "connection broken",
    "remote end closed",
    "remotedisconnected",
    "forcibly closed",
    "远程主机强迫关闭",
    "broken pipe",
    "recv failure",
    "curl: (56)",
    "connection was reset",
    "incompleteread",
    "incomplete read",
    "response ended prematurely",
    "peer closed connection",
)
_IMPERSONATE_DROP = {"user-agent", "sec-ch-ua", "sec-ch-ua-mobile", "sec-ch-ua-platform"}


def is_conn_reset(exc: BaseException) -> bool:
    """是否为「对端掐连接」类错误（Windows 10054 / RST / 断管道）。

    这类错误在行情源上很常见、且几乎总是瞬时的，值得再试几次。
    """
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if isinstance(cur, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
            return True
        text = str(cur).lower()
        if any(marker in text for marker in _RESET_MARKERS):
            return True
        cur = cur.__cause__ or cur.__context__
    return False


def retry_conn_reset(call, *, attempts: int = 3):
    """执行 ``call()``；只在断连类错误上重试，其余异常原样抛出。"""
    total = max(1, int(attempts))
    last: Exception | None = None
    for index in range(total):
        try:
            return call()
        except Exception as exc:  # noqa: BLE001
            last = exc
            if index >= total - 1 or not is_conn_reset(exc):
                raise
            time.sleep(0.5 * (index + 1) + random.uniform(0.0, 0.2))
    raise last  # pragma: no cover


def _impersonate_headers(headers: dict[str, str] | None) -> dict[str, str]:
    """curl_cffi impersonate 自带匹配的 UA；再塞一个过期 UA 会被巨潮拦成 403。"""
    out: dict[str, str] = {}
    for key, value in (headers or {}).items():
        if str(key).lower() in _IMPERSONATE_DROP:
            continue
        out[key] = value
    return out


def _session(*, verify: bool = True) -> requests.Session:
    sess = requests.Session()
    sess.trust_env = False
    sess.verify = verify
    sess.headers.update({"User-Agent": _UA})
    return sess


def _is_dns_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    if (
        "failed to resolve" in text
        or "getaddrinfo" in text
        or "nameresolution" in text
        or "11001" in text
        or "无法解析" in text
        or ("eastmoney.com" in text and "push2" in text)
    ):
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


def _push2_request(url: str) -> tuple[str, str]:
    """分片 push2（含 ``79.push2``）改连 delay 节点，Host/SNI 同步。"""
    parsed = urlparse(url)
    host = (parsed.hostname or "").strip().lower()
    canon = canonical_push2_host(host)
    if canon == host:
        return url, host
    port = f":{parsed.port}" if parsed.port else ""
    return urlunparse(parsed._replace(netloc=f"{canon}{port}")), canon


def _probe_timeout(
    timeout: int | tuple[float, float],
) -> tuple[float, float]:
    """多 IP 试连时收紧 connect，避免死节点拖满 6s×N。"""
    if isinstance(timeout, tuple):
        connect, read = float(timeout[0]), float(timeout[1])
    else:
        connect = read = float(timeout)
    return (min(connect, 2.5), read)


def _is_unreachable(exc: BaseException) -> bool:
    """WinError 10065 / 网络不可达：换 IP，短拉黑，别把整段候选打光。"""
    text = str(exc).lower()
    return any(
        token in text
        for token in (
            "10065",
            "network is unreachable",
            "host is unreachable",
            "无法连接的主机",
            "no route to host",
        )
    )


def _get_via_ip(
    url: str,
    *,
    params: dict[str, Any] | None,
    headers: dict[str, str] | None,
    timeout: int | tuple[float, float],
) -> requests.Response:
    url, host = _push2_request(url)
    ips = dial_ips(host)
    if not ips:
        raise requests.ConnectionError(f"无法解析 {host}")
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    last_error: Exception | None = None
    probe = _probe_timeout(timeout)
    tried: set[str] = set()
    unreachable = False

    def _attempt(candidates: list[str]) -> requests.Response | None:
        nonlocal last_error, unreachable
        for ip in candidates:
            if not ip or ip in tried:
                continue
            remaining = sum(1 for item in candidates if item and item not in tried)
            tried.add(ip)
            # 多 IP 试连一律收紧 connect，避免 10065/死节点拖满整页资金流
            wait = probe if remaining > 1 or len(tried) > 1 else timeout
            try:
                sess = _session(verify=False)
                sess.mount("https://", _SNIAdapter(host))
                hdrs = {"User-Agent": _UA, **(headers or {}), "Host": host}
                resp = sess.get(
                    _url_with_ip(url, ip),
                    params=params,
                    headers=hdrs,
                    timeout=wait,
                    allow_redirects=False,
                )
                resp.raise_for_status()
                remember_ip(host, ip)
                return resp
            except Exception as exc:  # noqa: BLE001
                drop_ip(host, ip)
                # 不可达 / 403 类：短拉黑，给其它边缘和新鲜 DNS 留机会
                ttl = 30.0 if _is_unreachable(exc) else None
                if _is_unreachable(exc):
                    unreachable = True
                if isinstance(exc, requests.HTTPError) and getattr(
                    exc.response, "status_code", 0
                ) in (403, 404):
                    ttl = 120.0
                mark_bad_ip(ip, host=host, ttl=ttl)
                last_error = exc
        return None

    resp = _attempt(ips)
    if resp is not None:
        return resp
    # 静态段 10065 / 全灭后：黑名单已生效，再 dial 一次走 recovery（新鲜 DNS）
    if unreachable or last_error is not None:
        resp = _attempt(dial_ips(host))
        if resp is not None:
            return resp
    forget_host(host)
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
    """GET；超时重试；东财 push2 优先 IP 直连，DNS 11001 时再走 DoH。"""
    if not verify:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    url, host = _push2_request(url)
    last_error: Exception | None = None
    attempts = max(1, int(retries) + 1)

    # Windows 上 push2* 系统 DNS 偶发 11001；先 IP 直连，避免等失败再兜底。
    if is_eastmoney_push2_host(host):
        try:
            resp = _get_via_ip(
                url, params=params, headers=headers, timeout=timeout
            )
            remember_host(host)
            return resp
        except Exception as exc:  # noqa: BLE001
            last_error = exc

    attempt = 0
    while True:
        try:
            sess = _session(verify=verify)
            resp = sess.get(
                url,
                params=params,
                headers=headers or {},
                timeout=timeout,
                allow_redirects=False,
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
            attempt += 1
            limit = attempts + (_CONN_RESET_EXTRA if is_conn_reset(exc) else 0)
            if attempt >= limit:
                raise
            time.sleep(min(2.0, 0.4 * attempt) + random.uniform(0.0, 0.2))
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

    def call() -> Any:
        resp = _get(
            url,
            params=params,
            headers=headers,
            timeout=timeout,
            retries=retries,
            verify=verify,
        )
        return resp.json()

    # 响应体读到一半被对端 RST（10054）时整段重取
    return retry_conn_reset(call, attempts=2)


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

    def call() -> str:
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

    # 响应体读到一半被对端 RST（10054）时整段重取
    return retry_conn_reset(call, attempts=2)


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

    if curl_requests is not None:
        # 不要覆盖 User-Agent：和 TLS 指纹不一致时，巨潮 WAF 直接 403。
        return retry_conn_reset(
            lambda: curl_requests.get(
                url,
                params=params,
                headers=_impersonate_headers(headers),
                timeout=timeout,
                impersonate="chrome",
            )
        )
    hdrs = {"User-Agent": _UA, **(headers or {})}
    return retry_conn_reset(
        lambda: _session().get(url, params=params, headers=hdrs, timeout=timeout)
    )


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

    if curl_requests is not None:
        # 不要覆盖 User-Agent：和 TLS 指纹不一致时，巨潮 WAF 直接 403。
        return retry_conn_reset(
            lambda: curl_requests.post(
                url,
                params=params,
                data=data,
                json=json_body,
                headers=_impersonate_headers(headers),
                timeout=timeout,
                impersonate="chrome",
            )
        )
    hdrs = {"User-Agent": _UA, **(headers or {})}
    return retry_conn_reset(
        lambda: _session().post(
            url,
            params=params,
            data=data,
            json=json_body,
            headers=hdrs,
            timeout=timeout,
        )
    )


def get_bytes(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 60,
) -> bytes:
    """GET 返回原始字节（公告 PDF 等）。优先 curl_cffi。"""

    def call() -> bytes:
        resp = browser_get(url, params=params, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return resp.content

    # 大文件读到一半被掐（10054）时整段重取一次
    return retry_conn_reset(call, attempts=2)
