"""阴跌→横盘→涨停筛选：后台任务 + 短缓存。"""

from __future__ import annotations

import threading
import time
from typing import Any

from analysis.config import DEFAULT_LOOKBACK_DAYS
from analysis.screen import screen_yindie

_CACHE_TTL = 300


class YindieScreenService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._status = "idle"
        self._result: dict[str, Any] | None = None
        self._error: str | None = None
        self._started_at = 0.0
        self._finished_at = 0.0
        self._job_key = ""

    @staticmethod
    def _make_key(days: int, top: int, force: bool) -> str:
        return f"d{days}:t{top}:f{int(force)}"

    def _cache_valid(self, key: str) -> bool:
        return (
            self._status == "done"
            and self._job_key == key
            and self._result is not None
            and time.time() - self._finished_at < _CACHE_TTL
        )

    def _snapshot(self, key: str) -> dict[str, Any]:
        elapsed = 0.0
        if self._started_at:
            end = self._finished_at or time.time()
            elapsed = round(end - self._started_at, 1)

        payload: dict[str, Any] = {
            "status": self._status,
            "elapsed_sec": elapsed,
        }
        if self._status == "done" and self._job_key == key:
            payload["data"] = self._result
        elif self._status == "error" and self._job_key == key:
            payload["error"] = self._error or "分析失败"
        elif self._status == "running" and self._job_key == key:
            payload["message"] = "正在拉取涨停池并分析 K 线，约需 1–3 分钟…"
        return payload

    def run_or_poll(
        self,
        *,
        days: int = DEFAULT_LOOKBACK_DAYS,
        top: int = 30,
        force: bool = False,
        workers: int = 8,
    ) -> dict[str, Any]:
        key = self._make_key(days, top, force)

        with self._lock:
            if not force and self._cache_valid(key):
                return self._snapshot(key)

            if self._status == "running" and self._job_key == key:
                return self._snapshot(key)

            self._status = "running"
            self._job_key = key
            self._result = None
            self._error = None
            self._started_at = time.time()
            self._finished_at = 0.0

        thread = threading.Thread(
            target=self._worker,
            args=(days, top, force, workers),
            daemon=True,
            name="yindie-screen",
        )
        thread.start()
        return self._snapshot(key)

    def _worker(self, days: int, top: int, force: bool, workers: int) -> None:
        try:
            limit = top if top > 0 else None
            result = screen_yindie(
                days=days,
                force=force,
                workers=workers,
                top=limit,
            )
            with self._lock:
                self._result = result
                self._status = "done"
                self._finished_at = time.time()
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self._status = "error"
                self._error = str(exc)
                self._finished_at = time.time()


service = YindieScreenService()
