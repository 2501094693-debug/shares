"""MACD 区间回测：后台任务 + 按参数落盘。"""

from __future__ import annotations

import threading
import time
from typing import Any

from analysis.macd.config import (
    DEFAULT_ADJUST,
    DEFAULT_BAND,
    DEFAULT_CROSS_TYPE,
    DEFAULT_FACTOR,
    DEFAULT_FAST,
    DEFAULT_INDEX,
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_NEAR_RATIO,
    DEFAULT_SIGNAL,
    DEFAULT_SLOW,
    DEFAULT_W_DIV,
    DEFAULT_W_PRIOR,
    DEFAULT_WORKERS,
    RANGE_CACHE_TAG,
)
from analysis.macd.range_scan import screen_macd_range
from analysis.persist import (
    KIND_MACD_RANGE,
    JobSlot,
    clear_disk,
    is_fresh,
    load_disk,
    save_disk,
)
from company.analysis.line.undulate.service import _iso


class MacdRangeScreenService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._slots: dict[str, JobSlot] = {}

    @staticmethod
    def _make_key(
        *,
        start: str,
        end: str,
        band: float,
        index: str,
        factor: str,
        lookback: int,
        adjust: str,
        near_ratio: float,
        fast: int,
        slow: int,
        signal: int,
        w_prior: float,
        w_div: float,
        cross_type: str = DEFAULT_CROSS_TYPE,
    ) -> str:
        band_s = f"{float(band):.4g}".replace(".", "p")
        near_s = f"{float(near_ratio):.4g}".replace(".", "p")
        wp = f"{float(w_prior):.2g}".replace(".", "p")
        wd = f"{float(w_div):.2g}".replace(".", "p")
        start_s = str(start or "").strip() or "na"
        end_s = str(end or "").strip() or "latest"
        ct_s = str(cross_type or "").strip().lower() or DEFAULT_CROSS_TYPE
        return (
            f"s{start_s}_e{end_s}_b{band_s}_i{index}_f{factor}"
            f"_l{lookback}_adj{adjust}_n{near_s}_m{fast}-{slow}-{signal}"
            f"_w{wp}-{wd}_ct{ct_s}_{RANGE_CACHE_TAG}"
        )

    def _progress(self, raw: dict[str, Any] | None) -> dict[str, Any]:
        data = raw or {}
        day_progress = data.get("day_progress") or {}
        return {
            "days_done": int(data.get("days_done") or 0),
            "days_total": int(data.get("days_total") or 0),
            "done": int(data.get("analyzed_count") or day_progress.get("done") or 0),
            "total": int(data.get("candidate_count") or day_progress.get("total") or 0),
            "day_done": int(day_progress.get("done") or 0),
            "day_total": int(day_progress.get("total") or 0),
            "phase": str(data.get("phase") or ""),
            "current_day": data.get("current_day"),
        }

    def _snapshot(self, slot: JobSlot) -> dict[str, Any]:
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
            payload["data"] = slot.result
            payload["progress"] = self._progress(slot.result)

        if slot.status == "running":
            progress = payload.get("progress") or {}
            phase = progress.get("phase") or ""
            done = int(progress.get("done") or 0)
            total = int(progress.get("total") or 0)
            days_total = int(progress.get("days_total") or 0)
            found = int((slot.result or {}).get("result_count") or 0)
            if phase == "gains":
                payload["message"] = "正在计算事后最大涨幅…"
            elif total:
                payload["message"] = (
                    f"已分析 {done}/{total}，命中 {found}"
                    + (f"（{days_total} 个交易日共用日线）" if days_total else "")
                )
            else:
                payload["message"] = "正在准备区间回测…"
        return payload

    def run_or_poll(
        self,
        *,
        start: str,
        end: str = "",
        band: float = DEFAULT_BAND,
        index: str = DEFAULT_INDEX,
        factor: str = DEFAULT_FACTOR,
        lookback: int = DEFAULT_LOOKBACK_DAYS,
        adjust: str = DEFAULT_ADJUST,
        near_ratio: float = DEFAULT_NEAR_RATIO,
        fast: int = DEFAULT_FAST,
        slow: int = DEFAULT_SLOW,
        signal: int = DEFAULT_SIGNAL,
        w_prior: float = DEFAULT_W_PRIOR,
        w_div: float = DEFAULT_W_DIV,
        cross_type: str = DEFAULT_CROSS_TYPE,
        force: bool = False,
        workers: int = DEFAULT_WORKERS,
    ) -> dict[str, Any]:
        start_key = _iso(start)
        end_key = _iso(end) if str(end or "").strip() else ""
        key = self._make_key(
            start=start_key,
            end=end_key,
            band=band,
            index=index,
            factor=factor,
            lookback=lookback,
            adjust=adjust,
            near_ratio=near_ratio,
            fast=fast,
            slow=slow,
            signal=signal,
            w_prior=w_prior,
            w_div=w_div,
            cross_type=cross_type,
        )

        with self._lock:
            slot = self._slots.get(key)
            # 非强制：已有进行中的任务则直接轮询；强制重跑则落到下方抬 run_id 重启
            if (
                not force
                and slot
                and slot.status == "running"
                and slot.run_id
            ):
                return self._snapshot(slot)
            if (
                not force
                and slot
                and slot.status == "done"
                and slot.result is not None
                and is_fresh(slot.finished_at)
            ):
                return self._snapshot(slot)
            need_disk = (not force) and (slot is None or slot.result is None)

        packed = load_disk(KIND_MACD_RANGE, key) if need_disk else None

        with self._lock:
            slot = self._slots.get(key) or JobSlot()
            if (
                not force
                and slot.status == "running"
                and slot.run_id
            ):
                return self._snapshot(slot)
            if packed and slot.result is None:
                cached_at, data = packed
                slot.result = data
                slot.finished_at = cached_at
                slot.started_at = cached_at
                slot.status = "done"
            if (
                not force
                and slot.status == "done"
                and slot.result is not None
                and is_fresh(slot.finished_at)
            ):
                self._slots[key] = slot
                return self._snapshot(slot)

            slot.run_id += 1
            run_id = slot.run_id
            slot.status = "running"
            slot.error = None
            # 强制重跑：内存结果清空；落盘在锁外删除
            slot.result = None
            slot.started_at = time.time()
            slot.finished_at = 0.0
            self._slots[key] = slot

        if force:
            clear_disk(KIND_MACD_RANGE, key)

        thread = threading.Thread(
            target=self._worker,
            args=(
                key,
                start_key,
                end_key,
                band,
                index,
                factor,
                lookback,
                adjust,
                near_ratio,
                fast,
                slow,
                signal,
                w_prior,
                w_div,
                cross_type,
                workers,
                force,
                run_id,
            ),
            daemon=True,
            name="macd-range-screen",
        )
        thread.start()
        with self._lock:
            return self._snapshot(self._slots[key])

    def _worker(
        self,
        key: str,
        start: str,
        end: str,
        band: float,
        index: str,
        factor: str,
        lookback: int,
        adjust: str,
        near_ratio: float,
        fast: int,
        slow: int,
        signal: int,
        w_prior: float,
        w_div: float,
        cross_type: str,
        workers: int,
        force: bool,
        run_id: int,
    ) -> None:
        def on_update(payload: dict[str, Any]) -> None:
            with self._lock:
                slot = self._slots.get(key)
                if not slot or slot.run_id != run_id:
                    return
                slot.result = payload

        try:
            result = screen_macd_range(
                start=start,
                end=end,
                band=band,
                index=index,
                factor=factor,
                lookback_days=lookback,
                adjust=adjust,
                near_ratio=near_ratio,
                fast=fast,
                slow=slow,
                signal=signal,
                w_prior=w_prior,
                w_div=w_div,
                cross_type=cross_type,
                workers=workers,
                force=force,
                on_update=on_update,
            )
            with self._lock:
                slot = self._slots.get(key)
                if not slot or slot.run_id != run_id:
                    return
                slot.result = result
                slot.status = "done"
                slot.finished_at = time.time()
            save_disk(KIND_MACD_RANGE, key, result)
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                slot = self._slots.get(key)
                if not slot or slot.run_id != run_id:
                    return
                slot.status = "error"
                slot.error = str(exc)
                slot.finished_at = time.time()


range_service = MacdRangeScreenService()
