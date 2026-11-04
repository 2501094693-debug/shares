"""Stop all backend server instances and free port 5000.

Handles the Windows edge case where uvicorn/multiprocessing leaves a child
holding the listen socket after the parent PID is already dead (netstat still
shows the dead parent PID as LISTENING).
"""
from __future__ import annotations

import ctypes
import os
import socket
import subprocess
import sys
import time


PORT = 5000
KERNEL32 = ctypes.windll.kernel32
PROCESS_TERMINATE = 0x0001


def _run(cmd: list[str], timeout: float = 30) -> str:
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        ).stdout or ""
    except Exception as exc:  # noqa: BLE001
        print(f"cmd failed: {cmd!r}: {exc}")
        return ""


def _listener_pids(port: int) -> set[int]:
    pids: set[int] = set()
    needle = f":{port}"
    for line in _run(["netstat", "-ano", "-p", "TCP"]).splitlines():
        if "LISTENING" not in line or needle not in line:
            continue
        parts = line.split()
        if len(parts) >= 5 and parts[-1].isdigit():
            pids.add(int(parts[-1]))
    return pids


def _iter_python_procs() -> list[tuple[int, str]]:
    out = _run(
        [
            "wmic",
            "process",
            "where",
            "name='python.exe'",
            "get",
            "ProcessId,CommandLine",
            "/FORMAT:LIST",
        ],
        timeout=60,
    )
    rows: list[tuple[int, str]] = []
    cmd = ""
    for raw in out.splitlines():
        line = raw.strip()
        if not line:
            if cmd and rows and rows[-1][1] == "":
                pass
            cmd = ""
            continue
        if line.startswith("CommandLine="):
            cmd = line[len("CommandLine=") :]
        elif line.startswith("ProcessId=") and line[len("ProcessId=") :].isdigit():
            rows.append((int(line[len("ProcessId=") :]), cmd))
            cmd = ""
    return rows


def _terminate(pid: int) -> None:
    me = os.getpid()
    if pid in (0, 4, me):
        return
    print(f"Killing PID {pid} ...")
    subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=30)
    h = KERNEL32.OpenProcess(PROCESS_TERMINATE, False, pid)
    if h:
        KERNEL32.TerminateProcess(h, 1)
        KERNEL32.CloseHandle(h)


def _port_free(port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def _is_server_cmd(cmd: str) -> bool:
    low = cmd.lower().replace("/", "\\")
    if "backend\\app.py" in low or low.rstrip().endswith("app.py") or "\\app.py" in low:
        return True
    if "uvicorn" in low and ("app:app" in low or "app.py" in low):
        return True
    return False


def _is_orphan_child(cmd: str, parent_pids: set[int]) -> bool:
    """multiprocessing child spawned by a (possibly already dead) server parent."""
    if "multiprocessing.spawn" not in cmd and "multiprocessing.fork" not in cmd:
        # also match: spawn_main(parent_pid=N
        if "spawn_main" not in cmd:
            return False
    for pid in parent_pids:
        if f"parent_pid={pid}" in cmd:
            return True
    return False


def stop_all(port: int = PORT) -> int:
    me = os.getpid()
    target_parents: set[int] = set()

    # Pass 1: explicit app.py / uvicorn servers
    for pid, cmd in _iter_python_procs():
        if pid == me:
            continue
        if _is_server_cmd(cmd):
            print(f"Found server {pid}: {cmd[:160]}")
            target_parents.add(pid)
            _terminate(pid)

    # Pass 2: whatever netstat says is LISTENING (may be a dead parent PID)
    listeners = _listener_pids(port)
    target_parents |= listeners
    for pid in sorted(listeners):
        _terminate(pid)

    # Pass 3: multiprocessing orphans that inherited the listen socket
    if target_parents:
        for pid, cmd in _iter_python_procs():
            if pid == me:
                continue
            if _is_orphan_child(cmd, target_parents):
                print(f"Found orphan child {pid}: {cmd[:160]}")
                _terminate(pid)

    # Pass 4: retry listeners until free
    for _ in range(12):
        if _port_free(port) and not _listener_pids(port):
            print(f"Port {port} is free.")
            return 0
        for pid in sorted(_listener_pids(port)):
            _terminate(pid)
            # also hunt orphans of this pid
            for cpid, cmd in _iter_python_procs():
                if cpid != me and _is_orphan_child(cmd, {pid}):
                    _terminate(cpid)
        time.sleep(0.25)

    if _port_free(port):
        print(f"Port {port} is free.")
        return 0

    print(f"WARNING: port {port} still busy. listeners={sorted(_listener_pids(port))}")
    return 1


if __name__ == "__main__":
    sys.exit(stop_all())
