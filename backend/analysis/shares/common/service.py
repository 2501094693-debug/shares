"""日线条件筛选：后台任务 + 落盘缓存。"""

from __future__ import annotations

import threading
import time
from typing import Any

from analysis.persist import KIND_SHARES, JobSlot, is_fresh, load_disk, save_disk, strip_charts
from analysis.shares.common.conditions import (
    normalize_day_specs,
    normalize_logic,
    specs_fingerprint,
)
from analysis.shares.common.view import apply_view
from analysis.shares.compare import (
    compare_fingerprint,
    load_compare_scheme,
    normalize_compare_params,
    screen_compare,
)
from analysis.shares.compose import (
    load_compose_tree,
    normalize_compose_params,
    screen_compose,
    tree_fingerprint,
)
from analysis.shares.pattern import (
    load_pattern_scheme,
    normalize_pattern_params,
    scheme_fingerprint,
    screen_scheme,
)
from analysis.shares.screen import screen_shares


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

    def _start_or_poll(
        self,
        *,
        fingerprint: str,
        code: str,
        top: int,
        force: bool,
        worker_target: Any,
        worker_args: tuple[Any, ...],
        thread_name: str,
    ) -> dict[str, Any]:
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
            target=worker_target,
            args=(*worker_args, key, run_id),
            daemon=True,
            name=thread_name,
        )
        thread.start()
        with self._lock:
            return self._snapshot(self._slots[key], top)

    def run_or_poll(
        self,
        *,
        day_specs: list[dict[str, Any]] | None = None,
        logic: str = "and",
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

        mode = normalize_logic(logic)
        fingerprint = specs_fingerprint(specs, mode)
        return self._start_or_poll(
            fingerprint=fingerprint,
            code=code,
            top=top,
            force=force,
            worker_target=self._worker,
            worker_args=(specs, mode, code, workers),
            thread_name="shares-day-screen",
        )

    def run_or_poll_pattern(
        self,
        *,
        params: dict[str, Any] | None = None,
        top: int = 50,
        code: str = "",
        force: bool = False,
        workers: int = 8,
    ) -> dict[str, Any]:
        normalized = normalize_pattern_params(params)
        try:
            scheme = load_pattern_scheme(normalized)
        except (FileNotFoundError, ValueError, TypeError) as exc:
            return {
                "status": "error",
                "error": str(exc),
                "elapsed_sec": 0,
            }
        fingerprint = f"pat_{scheme_fingerprint(scheme)}"
        return self._start_or_poll(
            fingerprint=fingerprint,
            code=code,
            top=top,
            force=force,
            worker_target=self._pattern_worker,
            worker_args=(normalized, code, workers),
            thread_name="shares-pattern-screen",
        )

    def run_or_poll_compare(
        self,
        *,
        params: dict[str, Any] | None = None,
        top: int = 50,
        code: str = "",
        force: bool = False,
        workers: int = 8,
    ) -> dict[str, Any]:
        try:
            normalized = normalize_compare_params(params)
            scheme = load_compare_scheme(normalized)
        except (ValueError, TypeError) as exc:
            return {
                "status": "error",
                "error": str(exc),
                "elapsed_sec": 0,
            }
        fingerprint = f"cmp_{compare_fingerprint(scheme)}"
        return self._start_or_poll(
            fingerprint=fingerprint,
            code=code,
            top=top,
            force=force,
            worker_target=self._compare_worker,
            worker_args=(normalized, code, workers),
            thread_name="shares-compare-screen",
        )

    def run_or_poll_compose(
        self,
        *,
        params: dict[str, Any] | None = None,
        top: int = 50,
        code: str = "",
        force: bool = False,
        workers: int = 8,
    ) -> dict[str, Any]:
        try:
            normalized = normalize_compose_params(params)
            tree = load_compose_tree(normalized)
        except (ValueError, TypeError) as exc:
            return {
                "status": "error",
                "error": str(exc),
                "elapsed_sec": 0,
            }
        fingerprint = f"ast_{tree_fingerprint(tree)}"
        return self._start_or_poll(
            fingerprint=fingerprint,
            code=code,
            top=top,
            force=force,
            worker_target=self._compose_worker,
            worker_args=(normalized, code, workers),
            thread_name="shares-compose-screen",
        )

    def _worker(
        self,
        specs: list[dict[str, Any]],
        logic: str,
        code: str,
        workers: int,
        key: str,
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
                logic=logic,
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

    def _pattern_worker(
        self,
        params: dict[str, Any],
        code: str,
        workers: int,
        key: str,
        run_id: int,
    ) -> None:
        def on_update(payload: dict[str, Any]) -> None:
            with self._lock:
                slot = self._slots.get(key)
                if not slot or slot.run_id != run_id:
                    return
                slot.result = payload

        try:
            scheme = load_pattern_scheme(params)
            result = screen_scheme(
                scheme,
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

    def _compare_worker(
        self,
        params: dict[str, Any],
        code: str,
        workers: int,
        key: str,
        run_id: int,
    ) -> None:
        def on_update(payload: dict[str, Any]) -> None:
            with self._lock:
                slot = self._slots.get(key)
                if not slot or slot.run_id != run_id:
                    return
                slot.result = payload

        try:
            scheme = load_compare_scheme(params)
            result = screen_compare(
                scheme,
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

    def _compose_worker(
        self,
        params: dict[str, Any],
        code: str,
        workers: int,
        key: str,
        run_id: int,
    ) -> None:
        def on_update(payload: dict[str, Any]) -> None:
            with self._lock:
                slot = self._slots.get(key)
                if not slot or slot.run_id != run_id:
                    return
                slot.result = payload

        try:
            tree = load_compose_tree(params)
            result = screen_compose(
                tree,
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
