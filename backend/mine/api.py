"""自选股票分组 HTTP 路由。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Query

from core.api import err, ok
from core.codes import safe_str
from mine.service import service

router = APIRouter()


def _parse_codes(payload: dict[str, Any] | None = None, codes_q: str = "") -> list[str]:
    """从 body.codes / body.code / query codes 解析股票代码列表。"""
    body = payload or {}
    raw: list[Any] = []
    if isinstance(body.get("codes"), list):
        raw.extend(body["codes"])
    single = body.get("code")
    if single is not None and safe_str(single):
        raw.append(single)
    if codes_q.strip():
        raw.extend(part for part in codes_q.replace("，", ",").split(",") if part.strip())
    return [safe_str(c) for c in raw if safe_str(c)]


@router.get("/api/mine/groups")
def list_groups():
    """列出全部分组（不含成分明细，仅 count）。"""
    try:
        return ok(service.list_groups())
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.post("/api/mine/groups")
def create_group(payload: dict[str, Any] = Body(default_factory=dict)):
    """新建分组。Body: ``{ "name": "自选" }``。"""
    name = safe_str((payload or {}).get("name"))
    try:
        return ok(service.create_group(name))
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/mine/groups/{group_id}")
def get_group(group_id: str):
    """分组详情（含股票列表）。"""
    try:
        return ok(service.get_group(group_id))
    except KeyError as exc:
        return err(str(exc), 404)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.delete("/api/mine/groups/{group_id}")
def delete_group(group_id: str):
    """删除分组及其全部股票。"""
    try:
        return ok(service.delete_group(group_id))
    except KeyError as exc:
        return err(str(exc), 404)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.post("/api/mine/groups/{group_id}/stocks")
def add_stocks(group_id: str, payload: dict[str, Any] = Body(default_factory=dict)):
    """向分组添加股票。

    Body 示例::

        { "codes": ["600519", "000001"] }
        { "code": "600519", "name": "贵州茅台" }
        { "codes": ["600519"], "names": {"600519": "贵州茅台"} }
    """
    codes = _parse_codes(payload)
    names_raw = (payload or {}).get("names")
    names: dict[str, str] = {}
    if isinstance(names_raw, dict):
        names = {safe_str(k): safe_str(v) for k, v in names_raw.items()}
    single_name = safe_str((payload or {}).get("name"))
    if single_name and len(codes) == 1:
        names.setdefault(codes[0], single_name)

    try:
        return ok(service.add_stocks(group_id, codes, names=names or None))
    except KeyError as exc:
        return err(str(exc), 404)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.delete("/api/mine/groups/{group_id}/stocks")
def remove_stocks(
    group_id: str,
    payload: dict[str, Any] = Body(default_factory=dict),
    codes: str = Query("", description="逗号分隔代码，可与 body 并用"),
):
    """从分组移除股票。Body: ``{ "codes": ["600519"] }`` 或 query ``codes=600519,000001``。"""
    parsed = _parse_codes(payload, codes)
    try:
        return ok(service.remove_stocks(group_id, parsed))
    except KeyError as exc:
        return err(str(exc), 404)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)
