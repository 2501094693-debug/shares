"""同步到同花顺账号 HTTP 路由（挂到 mine router 下）。"""

from __future__ import annotations

from fastapi import APIRouter

from core.api import err, ok

from mine.synchro.service import synchro_service

router = APIRouter()


@router.get("/api/mine/synchro/ths/status")
def ths_status():
    try:
        return ok(synchro_service.status())
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/mine/synchro/ths/remote")
def ths_remote():
    try:
        return ok(synchro_service.remote_groups())
    except PermissionError as exc:
        return err(str(exc), 401)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.post("/api/mine/synchro/ths/push")
def ths_push_all():
    try:
        return ok(synchro_service.push_all())
    except PermissionError as exc:
        return err(str(exc), 401)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.post("/api/mine/synchro/ths/push/{group_id}")
def ths_push_one(group_id: str):
    try:
        return ok(synchro_service.push_group(group_id))
    except KeyError as exc:
        return err(str(exc), 404)
    except ValueError as exc:
        return err(str(exc), 400)
    except PermissionError as exc:
        return err(str(exc), 401)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)
