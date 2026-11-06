"""委托盘口 HTTP 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from core.api import err, ok

from company.line.entrust.service import fetch_entrust

router = APIRouter()


@router.get("/api/stocks/entrust")
def stocks_entrust(
    code: str = Query("", description="股票代码，如 600519"),
    scope: str = Query(
        "all",
        description="book=买卖档 | levels=分价表 | all=两者（有 L2 时含 queues）",
    ),
    depth: str = Query("5", description="盘口深度，当前 thsdk 仅支持 5"),
    source: str = Query(
        "auto",
        description="auto=thsdk 优先 HQ 兜底 | thsdk | hq",
    ),
):
    """个股委托盘口：五档总量 + 分价表；Level-2 开通后附带委托单细则。"""
    code = code.strip()
    if not code:
        return err("缺少参数 code", 400)
    try:
        data = fetch_entrust(code, scope=scope.strip(), depth=depth.strip(), source=source.strip())
        return ok(data)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)
