"""三级行业轮动日历：结果按交易日复用。"""

from __future__ import annotations

import threading
import time
from typing import Any

from analysis.persist import KIND_ROTATION, JobSlot, is_fresh, load_disk, save_disk
from analysis.rotation.calendar import apply_top, screen_rotation
from analysis.rotation.config import CACHE_TAG, DEFAULT_LOOKBACK_DAYS, KLINE_WORKERS


class RotationScreenService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._slots: dict[str, JobSlot] = {}

    @staticmethod
    def _make_key(days: int) -> str:
        return f"d{days}_{CACHE_TAG}"

    def _snapshot(self, slot: JobSlot, top: int) -> dict[str, Any]:
        elapsed = 0.0
        if slot.started_at:
            end = slot.finished_at or time.time()
            elapsed = round(end - slot.started_at, 1)
        payload: dict[str, Any] = {
            "status": slot.status,
            "elapsed_sec": elapsed,
        }
        if slot.status == "error":
            payload["error"] = slot.error or "分析失败"
            return payload
        if slot.result is not None and slot.status in ("running", "done"):
            payload["data"] = apply_top(slot.result, None)
        if slot.status == "running":
            payload["message"] = "正在统计三级行业每天谁轮到了…"
        return payload

    def run_or_poll(
        self,
        *,
        days: int = DEFAULT_LOOKBACK_DAYS,
        top: int = 0,
        force: bool = False,
        workers: int = KLINE_WORKERS,
    ) -> dict[str, Any]:
        key = self._make_key(days)
        with self._lock:
            slot = self._slots.get(key)
            if not force and slot and slot.status == "done" and slot.result is not None:
                return self._snapshot(slot, top)
            if slot and slot.status == "running":
                return self._snapshot(slot, top)
            if not force:
                cached = load_disk(KIND_ROTATION, key)
                if cached is not None:
                    cached_at, data = cached
                    if is_fresh(cached_at):
                        slot = slot or JobSlot()
                        slot.status = "done"
                        slot.result = data
                        slot.started_at = cached_at
                        slot.finished_at = cached_at
                        self._slots[key] = slot
                        return self._snapshot(slot, top)
            slot = slot or JobSlot()
            slot.status = "running"
            slot.error = None
            slot.started_at = time.time()
            slot.finished_at = 0.0
            slot.run_id += 1
            run_id = slot.run_id
            self._slots[key] = slot

        def work() -> None:
            try:
                data = screen_rotation(days=days, force=force, workers=workers)
                # 重新分析只跳过整表结果缓存；已冻结的三级日面板仍复用。
                save_disk(KIND_ROTATION, key, data)
                with self._lock:
                    current = self._slots.get(key)
                    if current is None or current.run_id != run_id:
                        return
                    current.result = data
                    current.status = "done"
                    current.finished_at = time.time()
            except Exception as exc:  # noqa: BLE001
                with self._lock:
                    current = self._slots.get(key)
                    if current is None or current.run_id != run_id:
                        return
                    current.status = "error"
                    current.error = str(exc)
                    current.finished_at = time.time()

        threading.Thread(target=work, daemon=True, name="rotation-calendar").start()
        with self._lock:
            return self._snapshot(self._slots[key], top)


service = RotationScreenService()
