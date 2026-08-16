"""进程内 TTL 缓存。

盘口、K 线、分时都是「短 TTL + 按代码/周期当 key」。
存取时对 dict 做浅拷贝，避免调用方改返回值污染缓存。
"""

from __future__ import annotations

import threading
import time
from typing import Any


class TtlCache:
    """线程安全的 ``key → (写入时间, 值)`` 字典。"""

    def __init__(self, ttl_sec: float) -> None:
        self._ttl = ttl_sec
        self._lock = threading.Lock()
        self._items: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        """命中且未过期则返回拷贝；否则 None。"""
        now = time.time()
        with self._lock:
            hit = self._items.get(key)
            if not hit:
                return None
            stamped_at, value = hit
            if now - stamped_at >= self._ttl:
                return None
            return dict(value) if isinstance(value, dict) else value

    def put(self, key: str, value: Any, *, cached_at: float | None = None) -> None:
        """写入。``cached_at`` 可传入请求开始时间，让 TTL 从发起时算起。"""
        stored = dict(value) if isinstance(value, dict) else value
        with self._lock:
            self._items[key] = (cached_at if cached_at is not None else time.time(), stored)
