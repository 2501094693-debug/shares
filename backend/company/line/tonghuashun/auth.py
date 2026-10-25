"""同花顺扫码登录会话管理：二维码上屏 + 尽量少扫码。

原理（thsdk ``session.py``）：
- ``auth_qrcode`` 先尝试 ``session_dir/account.session`` 复用，成功则直接
  返回 ``authenticated``，不弹二维码；
- 复用失败才下发一次性 ``{scan_url, image_url}`` 挑战，需手机扫码。

本模块：
1. 会话目录固定 ``backend/cache/thsdk``，多天有效，避免换 cwd 反复扫码；
2. ``ensure()`` 只做快速复用探测，探测完立刻 ``cancel``，绝不在 native 侧
   留下悬挂的挑战任务（悬挂任务会挤占后继扫码任务，导致无二维码）；
3. 同一时刻只允许一个扫码任务（``_job_lock``），二维码存内存供前端轮询。
"""

from __future__ import annotations

import logging
import math
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SESSION_DIR = Path(__file__).resolve().parents[4] / "cache" / "thsdk"

_lock = threading.RLock()
_job_lock = threading.Lock()
_state: dict[str, Any] = {
    "authenticated": False,
    "pending": False,
    "image_url": "",
    "scan_url": "",
    "started_at": 0.0,
    "deadline": 0.0,
    "error": "",
}
_worker: threading.Thread | None = None
_stop = threading.Event()


def _client():
    from thsdk import session as _session

    client = _session._get_client()
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    try:
        client.session_dir = SESSION_DIR
    except Exception:
        pass
    return client


def _is_ok(state: Any) -> bool:
    return bool(isinstance(state, dict) and (state.get("authenticated") or state.get("state") == "authenticated"))


def _mark_authenticated(client) -> None:
    """native 已认会话：必须同时置 thsdk 进程客户端的 ``_authenticated``。

    直接调 ``runtime.call`` 会绕过官方 ``auth_qrcode()`` 包装，后者才负责
    置该标记；不补的话 ``klines`` 等数据调用会被 ``_request`` 以
    ``NotAuthenticatedError`` 拦掉，只能 fallback 到腾讯/东财。
    """
    try:
        with client._state_lock:
            client._authenticated = True
    except Exception:
        pass
    with _lock:
        _state.update(authenticated=True, pending=False, image_url="", scan_url="", error="")


def _unwrap(resp: Any) -> tuple[dict[str, Any], str]:
    """拆 ``runtime.call`` 的 ``{ok, data, error}`` 信封；出错返回 (\"\", \"code: msg\")。"""
    if not isinstance(resp, dict):
        return {}, f"native 返回非 dict：{type(resp).__name__}"
    if resp.get("ok"):
        data = resp.get("data")
        return data if isinstance(data, dict) else {}, ""
    err = resp.get("error") or {}
    if isinstance(err, dict):
        return {}, f"{err.get('code', 'unknown_error')}: {err.get('message', '')}"
    return {}, str(err)


def _store_challenge(state: Any) -> bool:
    if not isinstance(state, dict):
        return False
    img, url = str(state.get("image_url") or ""), str(state.get("scan_url") or "")
    if img or url:
        with _lock:
            _state["image_url"] = img
            _state["scan_url"] = url
        return True
    return False


def _cancel_quiet(client) -> None:
    try:
        client.runtime.call("auth_qrcode", {"cancel": True}, timeout_ms=5000)
    except Exception:
        pass


def status() -> dict[str, Any]:
    with _lock:
        snap = dict(_state)
    if snap["pending"] and snap["deadline"] and time.monotonic() > snap["deadline"]:
        with _lock:
            _state["pending"] = False
            _state["error"] = _state["error"] or "二维码已过期，请重新发起登录"
            _state["image_url"] = ""
            _state["scan_url"] = ""
            snap = dict(_state)
    return snap


def is_authenticated() -> bool:
    with _lock:
        return bool(_state["authenticated"])


def ensure(timeout: float = 3.0) -> bool:
    """数据请求前调用：已认证/复用成功 True，否则 False。绝不留下悬挂任务。"""
    if is_authenticated():
        return True
    if _stop.is_set() or status()["pending"]:
        return is_authenticated()
    if not _job_lock.acquire(blocking=False):
        return is_authenticated()
    try:
        try:
            client = _client()
        except Exception as exc:
            # 未安装 thsdk 等：当作未登录，交给腾讯/东财
            logger.debug("ths 客户端不可用: %s", exc)
            return False
        try:
            resp = client.runtime.call(
                "auth_qrcode",
                {
                    "session_dir": str(SESSION_DIR),
                    "timeout_seconds": 8,
                    "poll_interval_ms": 500,
                },
                timeout_ms=8000,
            )
            state, err_msg = _unwrap(resp)
        except Exception as exc:
            logger.debug("ths 会话探测失败: %s", exc)
            return False
        if err_msg:
            logger.debug("ths 会话探测被拒: %s", err_msg)
            return False
        if _is_ok(state):
            _mark_authenticated(client)
            return True
        _cancel_quiet(client)
        return False
    finally:
        _job_lock.release()


def _run_job(timeout: float, poll_interval: float) -> None:
    with _job_lock:
        client = _client()
        deadline = time.monotonic() + timeout
        try:
            resp = client.runtime.call(
                "auth_qrcode",
                {
                    "session_dir": str(SESSION_DIR),
                    "timeout_seconds": max(1, math.ceil(timeout)),
                    "poll_interval_ms": max(500, int(poll_interval * 1000)),
                },
                timeout_ms=20000,
            )
            state, err_msg = _unwrap(resp)
        except Exception as exc:
            logger.warning("ths 扫码任务启动失败: %s", exc)
            with _lock:
                _state["pending"] = False
                _state["error"] = f"扫码任务启动失败：{exc}"
            return
        if err_msg:
            logger.warning("ths 扫码任务被拒: %s", err_msg)
            with _lock:
                _state["pending"] = False
                _state["error"] = f"同花顺拒绝扫码任务：{err_msg}"
            return
        if _is_ok(state):
            _mark_authenticated(client)
            return
        if not _store_challenge(state):
            keys = sorted(state.keys()) if isinstance(state, dict) else type(state).__name__
            logger.warning("ths 下发挑战无二维码字段: %s", keys)
            with _lock:
                _state["pending"] = False
                _state["error"] = f"同花顺未下发二维码（返回字段：{keys}），请稍后重试"
            _cancel_quiet(client)
            return
        with _lock:
            _state["deadline"] = deadline
        while not _stop.is_set():
            if time.monotonic() >= deadline:
                break
            try:
                resp = client.runtime.call(
                    "auth_qrcode",
                    timeout_ms=int(min(20000, max(1000, (deadline - time.monotonic()) * 1000))),
                )
                state, err_msg = _unwrap(resp)
            except Exception as exc:
                logger.warning("ths 扫码轮询失败: %s", exc)
                with _lock:
                    _state["pending"] = False
                    _state["error"] = f"扫码轮询失败：{exc}"
                return
            if err_msg:
                logger.warning("ths 扫码轮询被拒: %s", err_msg)
                with _lock:
                    _state["pending"] = False
                    _state["error"] = f"同花顺拒绝扫码轮询：{err_msg}"
                return
            _store_challenge(state)
            if _is_ok(state):
                _mark_authenticated(client)
                return
            time.sleep(min(max(0.5, poll_interval), max(0.1, deadline - time.monotonic())))
        _cancel_quiet(client)
        with _lock:
            if not _state["authenticated"]:
                _state["pending"] = False
                _state["error"] = _state["error"] or "二维码登录超时，请重新发起"


def start_login(timeout: float = 120.0) -> dict[str, Any]:
    """前端点击登录：已认证直接返回；否则拉起唯一的后台扫码任务并等首图。"""
    global _worker
    if ensure():
        return status()
    with _lock:
        if _state["pending"] and (_state["image_url"] or _state["scan_url"]):
            return dict(_state)
        if _worker is not None and _worker.is_alive():
            pass
        else:
            _state.update(pending=True, error="", started_at=time.monotonic(),
                          deadline=time.monotonic() + timeout, image_url="", scan_url="")
            _stop.clear()
            _worker = threading.Thread(target=_run_job, args=(timeout, 1.0), daemon=True)
            _worker.start()
    for _ in range(100):
        snap = status()
        if snap["image_url"] or snap["scan_url"] or snap["authenticated"] or snap["error"]:
            return snap
        time.sleep(0.1)
    return status()


def cancel() -> dict[str, Any]:
    _stop.set()
    try:
        _cancel_quiet(_client())
    finally:
        with _lock:
            _state["pending"] = False
            _state["image_url"] = ""
            _state["scan_url"] = ""
    return status()


def logout() -> dict[str, Any]:
    cancel()
    try:
        _client().logout()
    except Exception:
        pass
    with _lock:
        _state.update(authenticated=False, pending=False, image_url="", scan_url="", error="")
    return status()


def mark_need_auth() -> None:
    with _lock:
        _state["authenticated"] = False
