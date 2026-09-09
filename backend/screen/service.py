"""阴跌→横盘→涨停筛选：后台任务 + 短缓存（按日分批，结果流式回传）。"""

from __future__ import annotations

import threading
import time
from typing import Any

from analysis.config import DEFAULT_LOOKBACK_DAYS
from analysis.screen import apply_day_top, screen_yindie

_CACHE_TTL = 300  # 完成后短缓存，分析中走流式快照


class YindieScreenService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._status = "idle"
        self._result: dict[str, Any] | None = None
        self._error: str | None = None
        self._started_at = 0.0
        self._finished_at = 0.0
        self._job_key = ""
        self._run_id = 0

    @staticmethod
    def _make_key(days: int) -> str:
        return f"d{days}"

    def _cache_valid(self, key: str) -> bool:
        return (
            self._status == "done"
            and self._job_key == key
            and self._result is not None
            and time.time() - self._finished_at < _CACHE_TTL
        )

    def _progress(self, raw: dict[str, Any] | None) -> dict[str, int]:
        data = raw or {}
        return {
            "done": int(data.get("analyzed_count") or 0),
            "total": int(data.get("candidate_count") or 0),
        }

    def _snapshot(self, key: str, top: int) -> dict[str, Any]:
        elapsed = 0.0
        if self._started_at:
            end = self._finished_at or time.time()
            elapsed = round(end - self._started_at, 1)

        payload: dict[str, Any] = {
            "status": self._status,
            "elapsed_sec": elapsed,
        }
        if self._job_key != key:
            return payload

        if self._status == "error":
            payload["error"] = self._error or "分析失败"
            return payload

        if self._result is not None and self._status in ("running", "done"):
            raw = self._result
            payload["data"] = apply_day_top(raw, None if top <= 0 else top)
            payload["progress"] = self._progress(raw)

        if self._status == "running":
            progress = payload.get("progress") or {"done": 0, "total": 0}
            done = progress.get("done") or 0
            total = progress.get("total") or 0
            if total:
                payload["message"] = f"已分析 {done}/{total}，按当前结果实时排名"
            else:
                payload["message"] = "正在拉取涨停池…"
        return payload

    def run_or_poll(
        self,
        *,
        days: int = DEFAULT_LOOKBACK_DAYS,
        top: int = 30,
        force: bool = False,
        workers: int = 8,
    ) -> dict[str, Any]:
        key = self._make_key(days)

        with self._lock:
            if not force and self._cache_valid(key):
                return self._snapshot(key, top)

            if self._status == "running" and self._job_key == key:
                return self._snapshot(key, top)

            self._run_id += 1
            run_id = self._run_id
            self._status = "running"
            self._job_key = key
            self._result = None
            self._error = None
            self._started_at = time.time()
            self._finished_at = 0.0

        thread = threading.Thread(
            target=self._worker,
            args=(days, force, workers, run_id),
            daemon=True,
            name="yindie-screen",
        )
        thread.start()
        return self._snapshot(key, top)

    def _worker(self, days: int, force: bool, workers: int, run_id: int) -> None:
        def on_update(payload: dict[str, Any]) -> None:
            with self._lock:
                if self._run_id != run_id:
                    return
                self._result = payload

        try:
            result = screen_yindie(
                days=days,
                force=force,
                workers=workers,
                top=None,
                on_update=on_update,
            )
            with self._lock:
                if self._run_id != run_id:
                    return
                self._result = result
                self._status = "done"
                self._finished_at = time.time()
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                if self._run_id != run_id:
                    return
                self._status = "error"
                self._error = str(exc)
                self._finished_at = time.time()


service = YindieScreenService()
