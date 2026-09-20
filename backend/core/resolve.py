"""主机名解析：系统 DNS 失败时走阿里 JSON DoH，并缓存 A 记录。

Windows 上东财 ``push2*`` 经常 11001（getaddrinfo failed），
用 ``223.5.5.5`` 解析后按 IP + 原 Host/SNI 访问即可。
"""

from __future__ import annotations

import re
import socket
import threading
import time

import requests
import urllib3

_CACHE: dict[str, tuple[float, list[str]]] = {}
_TTL = 300.0
# 阿里 + Cloudflare；Windows 11001 时并行 screening 常同时打 DoH，加锁避免惊群。
_DOH_PROVIDERS: tuple[tuple[str, str], ...] = (
    ("223.5.5.5", "dns.alidns.com"),
    ("1.1.1.1", "cloudflare-dns.com"),
)
# 数字 push2 子域在 Windows 上偶发 11001；同 CDN 集群可复用 delay / 主域 IP。
PUSH2_DELAY_HOST = "push2delay.eastmoney.com"
_PUSH2_FALLBACK_HOSTS = (
    PUSH2_DELAY_HOST,
    "push2.eastmoney.com",
)
# DoH / 系统 DNS 全挂时兜底。只在当次请求使用，不写入缓存。
_PUSH2_STATIC_IPS = (
    "101.226.30.136",
    "103.220.167.67",
    "61.129.129.196",
)
_PUSH2_STATIC_BY_HOST: dict[str, tuple[str, ...]] = {
    PUSH2_DELAY_HOST: ("101.226.30.136", "103.220.167.67"),
    "push2.eastmoney.com": ("61.129.129.196", "101.226.30.136"),
    "push2ex.eastmoney.com": ("140.207.67.212",),
    "push2his.eastmoney.com": ("140.207.67.156",),
}
_DEAD_IPS = frozenset({"61.129.129.48"})
_NUMERIC_PUSH2 = re.compile(r"^\d+\.push2\.eastmoney\.com$")
_PUSH2_EXEMPT = frozenset(
    {PUSH2_DELAY_HOST, "push2his.eastmoney.com", "push2ex.eastmoney.com"}
)


def _is_numeric_push2(host: str) -> bool:
    return bool(_NUMERIC_PUSH2.match(host))


def _is_eastmoney_push2_host(host: str) -> bool:
    """``push2`` / ``push2delay`` / ``push2ex`` / ``71.push2`` 等行情节点。"""
    host = (host or "").strip().lower().rstrip(".")
    if not host.endswith(".eastmoney.com"):
        return False
    label = host[: -len(".eastmoney.com")]
    return label == "push2" or label.startswith("push2") or _is_numeric_push2(host)


def is_eastmoney_push2_host(host: str) -> bool:
    return _is_eastmoney_push2_host(host)


def _static_ips(host: str) -> tuple[str, ...]:
    host = (host or "").strip().lower().rstrip(".")
    if host in _PUSH2_STATIC_BY_HOST:
        return _PUSH2_STATIC_BY_HOST[host]
    if _is_eastmoney_push2_host(host):
        return _PUSH2_STATIC_IPS
    return ()


def is_eastmoney_push2_sharded(host: str) -> bool:
    """``79.push2`` 等数字分片；主域 ``push2`` 保留，避免和 delay 绑死同一 IP。"""
    host = (host or "").strip().lower().rstrip(".")
    if not host.endswith(".eastmoney.com") or host in _PUSH2_EXEMPT:
        return False
    return _is_numeric_push2(host)


def canonical_push2_host(host: str) -> str:
    """分片 push2 统一走 delay 节点，避免 Windows 解析 ``79.push2`` 等失败。"""
    host = (host or "").strip().lower().rstrip(".")
    if is_eastmoney_push2_sharded(host):
        return PUSH2_DELAY_HOST
    return host


def _is_ipv4(text: str) -> bool:
    parts = text.split(".")
    if len(parts) != 4:
        return False
    try:
        return all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)
    except ValueError:
        return False


def drop_ip(host: str, ip: str) -> None:
    """连接失败的地址从缓存剔除，避免 5 分钟内反复打到死节点。"""
    host = (host or "").strip().lower().rstrip(".")
    ip = (ip or "").strip()
    if not host or not ip:
        return
    hit = _CACHE.get(host)
    if not hit:
        return
    kept = [item for item in hit[1] if item != ip]
    if kept:
        _CACHE[host] = (hit[0], kept)
    else:
        _CACHE.pop(host, None)


def forget_host(host: str) -> None:
    host = (host or "").strip().lower().rstrip(".")
    if host:
        _CACHE.pop(host, None)


def resolve_ipv4(host: str) -> list[str]:
    """返回 IPv4 列表：内存缓存 → 系统 DNS → DoH。静态 IP 只作当次兜底，不缓存。"""
    host = (host or "").strip().lower().rstrip(".")
    if not host:
        return []
    if _is_ipv4(host):
        return [host]
    now = time.monotonic()
    hit = _CACHE.get(host)
    if hit and hit[0] > now and hit[1]:
        return list(hit[1])
    canon = canonical_push2_host(host)
    lookup_host = canon if canon != host else host
    ips = _usable(_lookup_ips(lookup_host))
    if not ips and lookup_host != host:
        ips = _usable(_lookup_ips(host))
    if not ips:
        ips = _usable(_push2_parent_ips(lookup_host))
    if ips:
        _CACHE[host] = (now + _TTL, ips)
        if lookup_host != host:
            _CACHE[lookup_host] = (now + _TTL, ips)
        return ips
    return _usable(list(_static_ips(lookup_host) or _static_ips(host)))


def _usable(ips: list[str]) -> list[str]:
    out: list[str] = []
    for ip in ips:
        if ip in _DEAD_IPS or ip in out:
            continue
        out.append(ip)
    return out


def _lookup_ips(host: str) -> list[str]:
    return _system_dns(host) or _doh(host)


def _push2_parent_ips(host: str) -> list[str]:
    if not _is_eastmoney_push2_host(host):
        return []
    for parent in _PUSH2_FALLBACK_HOSTS:
        if parent == host:
            continue
        # 只用实时 DNS，不用其它节点写入的静态 IP 缓存（push2ex ≠ push2delay）。
        ips = _lookup_ips(parent)
        if ips:
            return ips
    return []


def remember_host(host: str) -> None:
    """请求成功后记下系统 DNS，供随后 11001 时复用。"""
    host = (host or "").strip().lower().rstrip(".")
    if not host or _is_ipv4(host):
        return
    hit = _CACHE.get(host)
    if hit and hit[0] > time.monotonic() and hit[1]:
        return
    ips = _usable(_system_dns(host))
    if ips:
        _CACHE[host] = (time.monotonic() + _TTL, ips)


def _system_dns(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, 443, socket.AF_INET, socket.SOCK_STREAM)
    except OSError:
        return []
    out: list[str] = []
    for *_, sockaddr in infos:
        ip = sockaddr[0]
        if ip not in out:
            out.append(ip)
    return out


def _doh_once(host: str, doh_ip: str, doh_host: str) -> list[str]:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    sess = requests.Session()
    sess.trust_env = False
    sess.verify = False
    try:
        resp = sess.get(
            f"https://{doh_ip}/resolve",
            params={"name": host, "type": "A"},
            headers={
                "Host": doh_host,
                "Accept": "application/dns-json",
                "User-Agent": "Mozilla/5.0",
            },
            timeout=6,
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception:  # noqa: BLE001
        return []
    if not isinstance(payload, dict):
        return []
    out: list[str] = []
    for item in payload.get("Answer") or []:
        if not isinstance(item, dict):
            continue
        if int(item.get("type") or 0) != 1:
            continue
        data = str(item.get("data") or "").strip().rstrip(".")
        if _is_ipv4(data) and data not in out:
            out.append(data)
    return out


def _doh(host: str) -> list[str]:
    with _doh_lock:
        now = time.monotonic()
        hit = _CACHE.get(host)
        if hit and hit[0] > now and hit[1]:
            return list(hit[1])
        for doh_ip, doh_host in _DOH_PROVIDERS:
            ips = _doh_once(host, doh_ip, doh_host)
            if ips:
                _CACHE[host] = (now + _TTL, ips)
                return ips
    return []
