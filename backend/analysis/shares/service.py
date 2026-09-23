"""日线条件筛选：后台任务 + 落盘缓存。"""

from __future__ import annotations

import threading
import time
from typing import Any

from analysis.persist import KIND_SHARES, JobSlot, is_fresh, load_disk, save_disk, strip_charts
from analysis.shares.conditions import normalize_day_specs, specs_fingerprint
from analysis.shares.screen import apply_view, screen_shares


class SharesScreenService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._slots: dict[str, JobSlot] = {}

    @staticmethod
    def _make_key(fingerprint: str, code: str = "") -> str:
        return f"{fingerprint}_c{code or '-'}"

    def _progress(self, raw: dict[str, Any] | None) -> dict[str, int]:
        data = raw or {}
        return {
            "done": int(data.get("analyzed_count") or 0),
            "total": int(data.get("candidate_count") or 0),
        }

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
            raw = slot.result
            payload["data"] = strip_charts(apply_view(raw, None if top <= 0 else top))
            payload["progress"] = self._progress(raw)

        if slot.status == "running":
            progress = payload.get("progress") or {"done": 0, "total": 0}
            done = progress.get("done") or 0
            total = progress.get("total") or 0
            if total:
                payload["message"] = f"已分析 {done}/{total}，符合条件的实时更新"
            else:
                payload["message"] = "正在准备股票池…"
        return payload

    def run_or_poll(
        self,
        *,
        day_specs: list[dict[str, Any]] | None = None,
        top: int = 50,
        code: str = "",
        force: bool = False,
        workers: int = 8,
    ) -> dict[str, Any]:
        specs = normalize_day_specs(day_specs)
        if not specs:
            return {
                "status": "error",
                "error": "请至少为一天设置有效条件",
                "elapsed_sec": 0,
            }

        fingerprint = specs_fingerprint(specs)
        key = self._make_key(fingerprint, code)

        with self._lock:
            slot = self._slots.get(key)
            if slot and slot.status == "running" and slot.run_id:
                return self._snapshot(slot, top)
            if not force and slot and slot.status == "done" and slot.result is not None and is_fresh(slot.finished_at):
                return self._snapshot(slot, top)
            need_disk = slot is None or slot.result is None

        packed = load_disk(KIND_SHARES, key) if need_disk else None

        with self._lock:
            slot = self._slots.get(key) or JobSlot()
            if slot.status == "running" and slot.run_id:
                return self._snapshot(slot, top)
            if packed and slot.result is None:
                cached_at, data = packed
                # 磁盘结果条件指纹不一致则丢弃
                if str((data or {}).get("fingerprint") or "") == fingerprint:
                    slot.result = data
                    slot.finished_at = cached_at
                    slot.started_at = cached_at
                    slot.status = "done"
            if not force and slot.status == "done" and slot.result is not None and is_fresh(slot.finished_at):
                self._slots[key] = slot
                return self._snapshot(slot, top)

            slot.run_id += 1
            run_id = slot.run_id
            slot.status = "running"
            slot.error = None
            slot.started_at = time.time()
            slot.finished_at = 0.0
            self._slots[key] = slot

        thread = threading.Thread(
            target=self._worker,
            args=(key, specs, code, workers, run_id),
            daemon=True,
            name="shares-day-screen",
        )
        thread.start()
        with self._lock:
            return self._snapshot(self._slots[key], top)

    def _worker(
        self,
        key: str,
        specs: list[dict[str, Any]],
        code: str,
        workers: int,
        run_id: int,
    ) -> None:
        def on_update(payload: dict[str, Any]) -> None:
            with self._lock:
                slot = self._slots.get(key)
                if not slot or slot.run_id != run_id:
                    return
                slot.result = payload

        try:
            result = screen_shares(
                day_specs=specs,
                code=code,
                workers=workers,
                top=None,
                on_update=on_update,
            )
            with self._lock:
                slot = self._slots.get(key)
                if not slot or slot.run_id != run_id:
                    return
                slot.result = result
                slot.status = "done"
                slot.finished_at = time.time()
            save_disk(KIND_SHARES, key, result)
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                slot = self._slots.get(key)
                if not slot or slot.run_id != run_id:
                    return
                slot.status = "error"
                slot.error = str(exc)
                slot.finished_at = time.time()


service = SharesScreenService()
