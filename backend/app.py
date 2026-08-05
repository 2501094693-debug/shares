"""申万三级行业浏览器 — FastAPI 后端。"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

# 保证从仓库根目录启动 / PyCharm 调试时也能解析 core、news 等包
_BACKEND_DIR = Path(__file__).resolve().parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import uvicorn
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from news.agent import collect_important_news
from services.data_service import service

ROOT = _BACKEND_DIR.parent
FRONTEND = ROOT / "frontend"


def _running_under_debugger() -> bool:
    """检测是否在 PyCharm / pydevd 等调试器下运行。

    uvicorn reload 会二次启动进程；若启动命令路径含空格
    （如 D:\\Program Files\\JetBrains\\...），重载时可能拆断路径。
    调试场景下应关闭 reload。
    """
    if "pydevd" in sys.modules:
        return True
    if sys.gettrace() is not None:
        return True
    return False


def _ok(data: Any = None, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": True}
    if data is not None:
        payload["data"] = data
    payload.update(extra)
    return payload


def _err(message: str, status_code: int = 500) -> JSONResponse:
    return JSONResponse({"ok": False, "error": message}, status_code=status_code)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        service.get_tree()
        print("行业树加载完成")
    except Exception as exc:  # noqa: BLE001
        print(f"行业树预热失败（首次访问时将重试）: {exc}")

    try:
        service.start_build_stock_index(force=False)
        print("已启动公司索引同步")
    except Exception as exc:  # noqa: BLE001
        print(f"公司索引启动失败: {exc}")

    yield


app = FastAPI(
    title="申万三级行业浏览器",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"ok": True, "service": "sw-industry"}


@app.get("/api/industries")
def industries(refresh: str = Query("0")):
    force = refresh == "1"
    try:
        tree = service.get_tree(force_refresh=force)
        return _ok(tree)
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc), 500)


@app.get("/api/search")
def search(q: str = Query("")):
    try:
        results = service.search(q)
        return _ok(results)
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc), 500)


@app.get("/api/stocks/search")
def stocks_search(name: str = Query(""), code: str = Query("")):
    try:
        results = service.search_stocks(name=name, code=code)
        return _ok(results, index=service.get_index_status())
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc), 500)


@app.get("/api/stocks/index/status")
def stocks_index_status():
    return _ok(service.get_index_status())


@app.post("/api/stocks/index/rebuild")
def stocks_index_rebuild(
    force: str = Query("0"),
    refresh: str = Query("0"),
):
    do_force = force == "1" or refresh == "1"
    try:
        status = service.start_build_stock_index(force=do_force)
        return _ok(status)
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc), 500)


@app.get("/api/industries/{code:path}/stocks")
def industry_stocks(code: str, refresh: str = Query("0")):
    force = refresh == "1"
    try:
        data = service.get_constituents(code, force_refresh=force)
        return _ok(data)
    except KeyError as exc:
        return _err(str(exc), 404)
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc), 500)


@app.get("/api/stocks/profile")
def stocks_profile(
    code: str = Query(""),
    industry: str = Query(""),
    name: str = Query(""),
):
    code = code.strip()
    industry = industry.strip()
    name = name.strip()
    if not code:
        return _err("缺少参数 code", 400)
    try:
        data = service.get_stock_profile(code, industry_code=industry, name=name)
        return _ok(data)
    except ValueError as exc:
        return _err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc), 500)


@app.get("/api/stocks/news")
def stocks_news(
    code: str = Query(""),
    name: str = Query(""),
    refresh: str = Query("0"),
    days: int = Query(3, ge=1, le=800),
    kind: str = Query(""),
):
    code = code.strip()
    name = name.strip()
    force = refresh == "1"
    if not code:
        return _err("缺少参数 code", 400)
    try:
        data = collect_important_news(
            code,
            name,
            force_refresh=force,
            days=days,
            kind=kind,
        )
        return _ok(data)
    except ValueError as exc:
        return _err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc), 500)


@app.get("/")
def index():
    return FileResponse(FRONTEND / "industry" / "index.html")


@app.get("/company")
@app.get("/company.html")
def company_page():
    return FileResponse(FRONTEND / "company" / "company.html")


@app.get("/js/app.js")
def js_app():
    return FileResponse(FRONTEND / "industry" / "app.js", media_type="application/javascript")


@app.get("/js/company.js")
def js_company():
    return FileResponse(
        FRONTEND / "company" / "company.js", media_type="application/javascript"
    )


# Static assets after API / page routes.
app.mount("/css", StaticFiles(directory=str(FRONTEND / "shared" / "css")), name="css")


if __name__ == "__main__":
    # 调试器下关闭 reload，避免 Program Files 路径空格导致二次启动失败
    use_reload = not _running_under_debugger()
    uvicorn.run(
        "app:app",
        host="127.0.0.1",
        port=5000,
        reload=use_reload,
    )
