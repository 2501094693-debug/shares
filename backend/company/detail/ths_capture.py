"""同花顺手机端私有通道抓包辅助（mitmproxy addon）。

把手机设为代理指向 mitmdump，打开同花顺 App 的「成交明细」页面，
即可把原生 App 发出的请求与 WebSocket 帧落盘到 ``cache/ths_capture.jsonl``，
再从日志里还原出私有通道的 URL / 鉴权字段 / 消息格式。

用法::

    pip install mitmproxy
    mitmdump -s backend/company/detail/ths_capture.py -p 8080

手机 Wi-Fi 代理设为运行 mitmdump 的机器 IP:8080，安装 mitmproxy 证书后
打开同花顺 App。抓到数据后按 URL / Host 过滤日志即可。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

LOG_PATH = Path(__file__).resolve().parents[3] / "cache" / "ths_capture.jsonl"
_HOST_KEYWORDS = ("10jqka.com.cn", "ths", "hexin", "thsdk")


def _is_relevant(host: str, url: str) -> bool:
    text = (host or "") + " " + (url or "")
    return any(keyword in text for keyword in _HOST_KEYWORDS)


def _dump(obj: dict[str, Any]) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(obj, ensure_ascii=False) + "\n")
    except Exception:
        return


def _body(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray)):
        try:
            text = value.decode("utf-8", "replace")
        except Exception:
            text = repr(value)
    else:
        text = str(value)
    if len(text) > 4000:
        text = text[:4000] + "...<truncated>"
    return text


def request(flow: Any) -> None:
    host = (flow.request.host or "") if getattr(flow, "request", None) else ""
    url = (flow.request.pretty_url or "") if getattr(flow, "request", None) else ""
    if not _is_relevant(host, url):
        return
    _dump(
        {
            "ts": time.time(),
            "kind": "http_request",
            "method": flow.request.method,
            "host": host,
            "url": url,
            "headers": dict(flow.request.headers),
            "body": _body(flow.request.content),
        }
    )


def response(flow: Any) -> None:
    host = (flow.request.host or "") if getattr(flow, "request", None) else ""
    url = (flow.request.pretty_url or "") if getattr(flow, "request", None) else ""
    if not _is_relevant(host, url):
        return
    _dump(
        {
            "ts": time.time(),
            "kind": "http_response",
            "host": host,
            "url": url,
            "status": flow.response.status_code if getattr(flow, "response", None) else None,
            "headers": dict(flow.response.headers) if getattr(flow, "response", None) else {},
            "body": _body(flow.response.content if getattr(flow, "response", None) else None),
        }
    )


def websocket_start(flow: Any) -> None:
    host = (flow.request.host or "") if getattr(flow, "request", None) else ""
    url = (flow.request.pretty_url or "") if getattr(flow, "request", None) else ""
    if not _is_relevant(host, url):
        return
    _dump(
        {
            "ts": time.time(),
            "kind": "ws_start",
            "host": host,
            "url": url,
            "headers": dict(flow.request.headers),
        }
    )


def websocket_message(flow: Any) -> None:
    host = (flow.request.host or "") if getattr(flow, "request", None) else ""
    url = (flow.request.pretty_url or "") if getattr(flow, "request", None) else ""
    if not _is_relevant(host, url):
        return
    message = flow.websocket.messages[-1] if getattr(flow, "websocket", None) and flow.websocket.messages else None
    if message is None:
        return
    _dump(
        {
            "ts": time.time(),
            "kind": "ws_message",
            "host": host,
            "url": url,
            "from_client": bool(getattr(message, "from_client", False)),
            "content": _body(message.content),
            "dropped": bool(getattr(message, "dropped", False)),
        }
    )


def websocket_end(flow: Any) -> None:
    host = (flow.request.host or "") if getattr(flow, "request", None) else ""
    url = (flow.request.pretty_url or "") if getattr(flow, "request", None) else ""
    if not _is_relevant(host, url):
        return
    _dump(
        {
            "ts": time.time(),
            "kind": "ws_end",
            "host": host,
            "url": url,
        }
    )


def tcp_start(flow: Any) -> None:
    server = getattr(flow, "server_conn", None)
    host, port = getattr(server, "address", ("", 0)) or ("", 0)
    if port not in {80, 443, 8601, 8602, 9601, 9602, 9603} and not _is_relevant(str(host), ""):
        return
    _dump({"ts": time.time(), "kind": "tcp_start", "host": str(host), "port": int(port)})


def tcp_message(flow: Any) -> None:
    server = getattr(flow, "server_conn", None)
    host, port = getattr(server, "address", ("", 0)) or ("", 0)
    if port not in {80, 443, 8601, 8602, 9601, 9602, 9603} and not _is_relevant(str(host), ""):
        return
    messages = getattr(flow, "messages", None) or []
    if not messages:
        return
    message = messages[-1]
    content = message.content or b""
    _dump(
        {
            "ts": time.time(),
            "kind": "tcp_message",
            "host": str(host),
            "port": int(port),
            "from_client": bool(getattr(message, "from_client", False)),
            "len": len(content),
            "hex": content[:1024].hex(),
        }
    )


class ThsCapture:
    def request(self, flow: Any) -> None:
        request(flow)

    def response(self, flow: Any) -> None:
        response(flow)

    def websocket_start(self, flow: Any) -> None:
        websocket_start(flow)

    def websocket_message(self, flow: Any) -> None:
        websocket_message(flow)

    def websocket_end(self, flow: Any) -> None:
        websocket_end(flow)

    def tcp_start(self, flow: Any) -> None:
        tcp_start(flow)

    def tcp_message(self, flow: Any) -> None:
        tcp_message(flow)


addons = [ThsCapture()]


def _analyze() -> int:
    if not LOG_PATH.exists():
        print("no capture log:", LOG_PATH)
        return 0
    hosts: set[str] = set()
    urls: set[str] = set()
    ws_urls: set[str] = set()
    tcp_endpoints: set[tuple[str, int]] = set()
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        host = str(obj.get("host") or "")
        url = str(obj.get("url") or "")
        kind = str(obj.get("kind") or "")
        if kind.startswith("tcp"):
            if host:
                tcp_endpoints.add((host, int(obj.get("port") or 0)))
        elif kind.startswith("ws"):
            if url:
                ws_urls.add(url)
        else:
            if host:
                hosts.add(host)
            if url:
                urls.add(url)
    print("hosts:")
    for host in sorted(hosts):
        print("  ", host)
    print("ws urls:")
    for url in sorted(ws_urls):
        print("  ", url)
    print("tcp endpoints:")
    for host, port in sorted(tcp_endpoints):
        print(f"   {host}:{port}")
    print("http urls:")
    for url in sorted(urls)[:60]:
        print("  ", url)
    return 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="THS capture log analyzer")
    parser.add_argument("--analyze", action="store_true", help="analyze cache/ths_capture.jsonl")
    args = parser.parse_args()
    if args.analyze:
        raise SystemExit(_analyze())
    print("use mitmdump -s", __file__, "to capture")
