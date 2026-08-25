"""FastAPI 路由共用的 JSON 包装。"""

from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse


def ok(data: Any = None, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": True}
    if data is not None:
        payload["data"] = data
    payload.update(extra)
    return payload


def err(message: str, status_code: int = 500) -> JSONResponse:
    return JSONResponse({"ok": False, "error": message}, status_code=status_code)
