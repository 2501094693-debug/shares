"""申万三级行业浏览器 — FastAPI 后端。

三套业务：
- ``industry``：申万分类、成分股检索、地图标注
- ``company``：单只股票的盘口、K 线、资讯
- ``market``：申万行业涨跌、资金流向、个股涨跌榜、行业轮动
- ``world``：全球主要股指、央行利率、国债收益率、原油期货
- ``gmap``：Google Maps 全球检索与定位
- ``list``：龙虎榜个股历史上榜（公司详情页）
- ``funds.fund`` / ``funds.otc_fund``：统一基金页（场内 ETF/LOF + 场外开放式）
- ``analysis``：研判（涨跌停分析 / 个股分析 / 行业行情分析）
"""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# 保证从仓库根目录启动 / PyCharm 调试时也能解析 industry / company / agent / analysis
_BACKEND_DIR = Path(__file__).resolve().parent
_ROOT_DIR = _BACKEND_DIR.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))
if str(_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(_ROOT_DIR))

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from agent.api import router as ai_router
from company.api import router as company_router
from company.fundflow.api import router as fundflow_router
from company.news.financialreport.api import router as financialreport_router
from funds.fund.api import router as fund_router
from industry.api import router as industry_router
from industry.service import service as industry_service
from funds.fund.service import service as fund_service
from list.api import router as list_router
from market.api import router as market_router
from world.api import router as world_router
from analysis.api import router as screen_router
from funds.otc_fund.api import router as otc_fund_router
from funds.otc_fund.service import service as otc_fund_service

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

    try:
        fund_service.start_build_index(force=False)
        print("已启动场内基金索引同步")
    except Exception as exc:  # noqa: BLE001
        print(f"场内基金索引启动失败: {exc}")

    try:
        import threading

        threading.Thread(
            target=otc_fund_service.warmup_index,
            kwargs={"force": False},
            daemon=True,
            name="otc-fund-index-warmup",
        ).start()
        print("已启动场外基金索引同步")
    except Exception as exc:  # noqa: BLE001
        print(f"场外基金索引启动失败: {exc}")

    try:
        import threading

        from market.shares.service import service as shares_service
        from market.sw.service import service as market_service

        def _warmup_market() -> None:
            try:
                market_service.tree()
                print("行业行情树预热完成")
            except Exception as exc:  # noqa: BLE001
                print(f"行业行情树预热失败: {exc}")
            try:
                shares_service.list()
                print("个股行情预热完成")
            except Exception as exc:  # noqa: BLE001
                print(f"个股行情预热失败: {exc}")
            try:
                from market.steep.service import service as steep_service

                steep_service.recent(days=15)
                print("涨跌停预热完成")
            except Exception as exc:  # noqa: BLE001
                print(f"涨跌停预热失败: {exc}")

        threading.Thread(
            target=_warmup_market,
            daemon=True,
            name="market-tree-warmup",
        ).start()
        print("已启动行业/个股行情预热")
    except Exception as exc:  # noqa: BLE001
        print(f"行业行情预热启动失败: {exc}")

    try:
        from market.sw.history import start_snapshot_loop

        start_snapshot_loop()
        print("已启动行业行情每日快照")
    except Exception as exc:  # noqa: BLE001
        print(f"行业行情快照启动失败: {exc}")

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
app.include_router(fundflow_router)
app.include_router(financialreport_router)
app.include_router(market_router)
app.include_router(world_router)
app.include_router(list_router)
app.include_router(fund_router)
app.include_router(otc_fund_router)
app.include_router(ai_router)
app.include_router(screen_router)


@app.get("/api/health")
def health():
    return {"ok": True, "service": "sw-industry"}


@app.get("/")
def index(request: Request):
    qs = request.query_params
    if any(qs.get(key) for key in ("industry", "cname", "ccode")):
        target = "/industry"
        raw = request.url.query
        if raw:
            target = f"{target}?{raw}"
        return RedirectResponse(url=target, status_code=302)
    return FileResponse(
        FRONTEND / "world" / "index.html",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.get("/industry")
@app.get("/industry.html")
def industry_page():
    return FileResponse(
        FRONTEND / "industry" / "index.html",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.get("/cn")
def china_market_entry():
    return RedirectResponse(url="/market", status_code=302)


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


@app.get("/shares")
@app.get("/shares.html")
def shares_page():
    return FileResponse(
        FRONTEND / "shares" / "index.html",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.get("/js/shares.js")
def js_shares():
    return FileResponse(
        FRONTEND / "shares" / "app.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.get("/steep")
@app.get("/steep.html")
def steep_page():
    return FileResponse(
        FRONTEND / "steep" / "index.html",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.get("/js/steep.js")
def js_steep():
    return FileResponse(
        FRONTEND / "steep" / "app.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.get("/world")
@app.get("/world.html")
def world_page():
    return RedirectResponse(url="/", status_code=302)


@app.get("/js/world.js")
def js_world():
    return FileResponse(
        FRONTEND / "world" / "app.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.get("/gmap")
@app.get("/gmap.html")
def gmap_page():
    return FileResponse(
        FRONTEND / "gmap" / "index.html",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.get("/js/gmap.js")
def js_gmap():
    return FileResponse(
        FRONTEND / "gmap" / "app.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.get("/screen")
@app.get("/screen.html")
def screen_page():
    return RedirectResponse(url="/analysis?view=limit", status_code=302)


@app.get("/js/screen.js")
def js_screen():
    return FileResponse(
        FRONTEND / "screen" / "app.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.get("/analysis")
@app.get("/analysis.html")
def analysis_page():
    return FileResponse(
        FRONTEND / "analysis" / "index.html",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.get("/js/analysis.js")
def js_analysis():
    return FileResponse(
        FRONTEND / "analysis" / "app.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.get("/fund")
@app.get("/fund.html")
def fund_page():
    return FileResponse(
        FRONTEND / "fund" / "index.html",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.get("/js/fund.js")
def js_fund():
    return FileResponse(
        FRONTEND / "fund" / "app.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.get("/otc-fund")
@app.get("/otc-fund.html")
def otc_fund_page():
    return RedirectResponse("/fund?cat=gp", status_code=301)


@app.get("/js/otc-fund.js")
def js_otc_fund():
    return RedirectResponse("/js/fund.js", status_code=301)


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


@app.get("/ai")
@app.get("/ai.html")
@app.get("/earnings")
@app.get("/earnings.html")
@app.get("/competition")
@app.get("/competition.html")
@app.get("/risk")
@app.get("/risk.html")
def ai_page_removed():
    return RedirectResponse(url="/", status_code=302)


# Static assets after API / page routes.
app.mount("/css", StaticFiles(directory=str(FRONTEND / "shared" / "css")), name="css")
app.mount("/geo", StaticFiles(directory=str(FRONTEND / "shared" / "geo")), name="geo")
app.mount(
    "/js/shared",
    StaticFiles(directory=str(FRONTEND / "shared" / "js")),
    name="js_shared",
)
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
