"""申万三级行业浏览器 — FastAPI 后端。

三套业务：
- ``industry``：申万分类、成分股检索、地图标注
- ``company``：单只股票的盘口、K 线、资讯
- ``market``：申万行业涨跌、资金流向、行业轮动
"""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# 保证从仓库根目录启动 / PyCharm 调试时也能解析 industry / company
_BACKEND_DIR = Path(__file__).resolve().parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from company.api import router as company_router
from industry.api import router as industry_router
from industry.service import service as industry_service
from market.api import router as market_router

ROOT = _BACKEND_DIR.parent
FRONTEND = ROOT / "frontend"


def _load_dotenv() -> None:
    """轻量加载仓库根目录 .env（不覆盖已有环境变量）。"""
    path = ROOT / ".env"
    if not path.exists():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()


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


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        industry_service.get_tree()
        print("行业树加载完成")
    except Exception as exc:  # noqa: BLE001
        print(f"行业树预热失败（首次访问时将重试）: {exc}")

    try:
        industry_service.start_build_stock_index(force=False)
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

app.include_router(industry_router)
app.include_router(company_router)
app.include_router(market_router)


@app.get("/api/health")
def health():
    return {"ok": True, "service": "sw-industry"}


@app.get("/")
def index():
    return FileResponse(FRONTEND / "industry" / "index.html")


@app.get("/market")
@app.get("/market.html")
def market_page():
    return FileResponse(
        FRONTEND / "market" / "index.html",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.get("/js/market.js")
def js_market():
    return FileResponse(
        FRONTEND / "market" / "app.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.get("/steep")
@app.get("/steep.html")
def steep_page():
    return FileResponse(
        FRONTEND / "market" / "steep.html",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.get("/js/steep.js")
def js_steep():
    return FileResponse(
        FRONTEND / "market" / "steep.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.get("/company")
@app.get("/company.html")
def company_page():
    return FileResponse(
        FRONTEND / "company" / "company.html",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.get("/js/app.js")
def js_app():
    """兼容旧路径；行业页已改用 /js/industry/app.js（ES module）。"""
    return FileResponse(
        FRONTEND / "industry" / "app.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.get("/js/company.js")
def js_company():
    return FileResponse(
        FRONTEND / "company" / "company.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


# Static assets after API / page routes.
app.mount("/css", StaticFiles(directory=str(FRONTEND / "shared" / "css")), name="css")
app.mount("/geo", StaticFiles(directory=str(FRONTEND / "shared" / "geo")), name="geo")
# 行业页 ES modules：/js/industry/app.js → ./map/*.js
app.mount(
    "/js/industry",
    StaticFiles(directory=str(FRONTEND / "industry")),
    name="js_industry",
)


if __name__ == "__main__":
    # 调试器下关闭 reload，避免 Program Files 路径空格导致二次启动失败
    use_reload = not _running_under_debugger()
    uvicorn.run(
        "app:app",
        host="127.0.0.1",
        port=5000,
        reload=use_reload,
    )
