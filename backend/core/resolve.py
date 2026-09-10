"""主机名解析：系统 DNS 失败时走阿里 JSON DoH，并缓存 A 记录。

Windows 上东财 ``push2*`` 经常 11001（getaddrinfo failed），
用 ``223.5.5.5`` 解析后按 IP + 原 Host/SNI 访问即可。
"""

from __future__ import annotations

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
_doh_lock = threading.Lock()


def _is_ipv4(text: str) -> bool:
    parts = text.split(".")
    if len(parts) != 4:
        return False
    try:
        return all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)
    except ValueError:
        return False


def resolve_ipv4(host: str) -> list[str]:
    """返回 IPv4 列表：内存缓存 → 系统 DNS → 阿里 DoH。"""
    host = (host or "").strip().lower().rstrip(".")
    if not host:
        return []
    if _is_ipv4(host):
        return [host]
    now = time.monotonic()
    hit = _CACHE.get(host)
    if hit and hit[0] > now and hit[1]:
        return list(hit[1])
    ips = _system_dns(host) or _doh(host)
    if ips:
        _CACHE[host] = (now + _TTL, ips)
    return ips


def remember_host(host: str) -> None:
    """请求成功后记下系统 DNS，供随后 11001 时复用。"""
    host = (host or "").strip().lower().rstrip(".")
    if not host or _is_ipv4(host):
        return
    hit = _CACHE.get(host)
    if hit and hit[0] > time.monotonic() and hit[1]:
        return
    ips = _system_dns(host)
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
