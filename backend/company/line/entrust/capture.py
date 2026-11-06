"""手机端买卖队列抓包辅助。

复用 ``company.detail.ths_capture`` 的 mitmproxy addon；本模块只提供
「从落盘日志里筛队列相关 URL / 帧」的分析入口，方便对照 App 里的委托细则。

用法::

    mitmdump -s backend/company/detail/ths_capture.py -p 8080
    # 手机打开个股买卖队列页后：
    python -m company.line.entrust.capture --analyze
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

LOG_PATH = Path(__file__).resolve().parents[4] / "cache" / "ths_capture.jsonl"

_QUEUE_HINTS = (
    "queue",
    "order",
    "entrust",
    "delegate",
    "level2",
    "l2",
    "十档",
    "队列",
    "委托",
    "orderbook",
    "order_book",
    "depth",
    "bid",
    "ask",
)


def _looks_like_queue(text: str) -> bool:
    low = (text or "").lower()
    return any(hint in low for hint in _QUEUE_HINTS)


def analyze(path: Path | None = None) -> dict[str, Any]:
    """扫描抓包日志，挑出疑似买卖队列 / 委托相关的 HTTP / WS / TCP。"""
    log = path or LOG_PATH
    if not log.is_file():
        return {"path": str(log), "exists": False, "hits": []}

    hits: list[dict[str, Any]] = []
    hosts: set[str] = set()
    for line in log.read_text(encoding="utf-8").splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        blob = " ".join(
            str(obj.get(key) or "")
            for key in ("kind", "host", "url", "body", "content", "hex")
        )
        if not _looks_like_queue(blob):
            continue
        host = str(obj.get("host") or "")
        if host:
            hosts.add(host)
        hits.append(
            {
                "kind": obj.get("kind"),
                "host": host,
                "url": obj.get("url"),
                "port": obj.get("port"),
                "status": obj.get("status"),
                "len": obj.get("len"),
                "preview": (obj.get("body") or obj.get("content") or obj.get("hex") or "")[
                    :240
                ],
            }
        )
    return {
        "path": str(log),
        "exists": True,
        "hosts": sorted(hosts),
        "hit_count": len(hits),
        "hits": hits[:80],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="委托队列抓包日志分析")
    parser.add_argument("--analyze", action="store_true", help="分析 cache/ths_capture.jsonl")
    parser.add_argument("--log", default="", help="自定义抓包日志路径")
    args = parser.parse_args()
    if not args.analyze:
        print("use: python -m company.line.entrust.capture --analyze")
        print("first capture with: mitmdump -s backend/company/detail/ths_capture.py -p 8080")
        return 0
    pack = analyze(Path(args.log) if args.log else None)
    print(json.dumps(pack, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
