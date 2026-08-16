"""申万三级行业浏览器 — FastAPI 后端。"""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

# 保证从仓库根目录启动 / PyCharm 调试时也能解析 data / message 等包
_BACKEND_DIR = Path(__file__).resolve().parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import uvicorn
from fastapi import Body, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from data.data_service import service
from data.stocks.geo import enrich_codes
from data.stocks.kline import fetch_intraday, fetch_kline
from message.feed import collect_company_messages
from message.profile import query_company_profile
from message.taxonomy.constants import ALL_SECTIONS, DEFAULT_SECTIONS

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


@app.get("/api/stocks/kline")
def stocks_kline(
    code: str = Query("", description="股票代码，如 601881"),
    period: str = Query(
        "day",
        description="day|week|month|1m|5m|15m|30m|60m",
    ),
    adjust: str = Query("qfq", description="none|qfq|hfq"),
    limit: int = Query(320, ge=1, le=10000),
    beg: str = Query("", description="开始日期 YYYYMMDD 或 YYYY-MM-DD"),
    end: str = Query("", description="结束日期 YYYYMMDD 或 YYYY-MM-DD"),
    refresh: str = Query("0"),
):
    """日/周/月/分钟 K 线。腾讯优先，东财兜底。"""
    code = code.strip()
    if not code:
        return _err("缺少参数 code", 400)
    try:
        data = fetch_kline(
            code,
            period=period,
            adjust=adjust,
            limit=limit,
            beg=beg.strip(),
            end=end.strip(),
            force=refresh == "1",
        )
        return _ok(data)
    except ValueError as exc:
        return _err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc), 500)


@app.get("/api/stocks/intraday")
def stocks_intraday(
    code: str = Query("", description="股票代码，如 601881"),
    ndays: int = Query(1, description="1=当日分时，5=五日分时"),
    refresh: str = Query("0"),
):
    """分时走势（东财 trends2）。"""
    code = code.strip()
    if not code:
        return _err("缺少参数 code", 400)
    try:
        data = fetch_intraday(code, ndays=ndays, force=refresh == "1")
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
    days: int = Query(3, ge=1, le=20000),
    kind: str = Query(""),
):
    code = code.strip()
    name = name.strip()
    force = refresh == "1"
    if not code:
        return _err("缺少参数 code", 400)
    try:
        data = collect_company_messages(
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


@app.get("/api/stocks/profile-messages")
def stocks_profile_messages(
    code: str = Query("", description="股票代码或公司名"),
    name: str = Query(""),
    days: int = Query(90, ge=1, le=20000),
    sections: str = Query(
        "default",
        description=(
            "采集段：default="
            + ",".join(DEFAULT_SECTIONS)
            + "；all 或逗号组合="
            + ",".join(ALL_SECTIONS)
        ),
    ),
    max_pages: int = Query(3, ge=1, le=20),
):
    """系统性分类视图（disclosure/regulatory/press/news/research）。数据均来自 message。"""
    code = code.strip()
    name = name.strip()
    if not code:
        return _err("缺少参数 code", 400)
    try:
        data = query_company_profile(
            code,
            name=name,
            days=days,
            sections=sections,
            max_pages=max_pages,
        )
        return _ok(data)
    except ValueError as exc:
        return _err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc), 500)


@app.post("/api/stocks/geo-enrich")
def stocks_geo_enrich(payload: dict[str, Any] = Body(default_factory=dict)):
    """批量补齐公司全称与注册省市区。Body: { codes: string[], force?: 0|1 }。

    经纬度由前端高德 PlaceSearch 标注，本接口不返回可靠坐标。
    """
    raw_codes = payload.get("codes") or []
    if not isinstance(raw_codes, list):
        return _err("codes 须为数组", 400)
    codes = [str(c).strip() for c in raw_codes if str(c).strip()]
    if not codes:
        return _err("缺少 codes", 400)
    if len(codes) > 500:
        return _err("单次最多 500 个代码", 400)
    force = str(payload.get("force") or "0") in {"1", "true", "True"}
    try:
        items = enrich_codes(codes, force=force, max_workers=4)
        return _ok({"items": items, "count": len(items)})
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc), 500)


@app.get("/api/map/config")
def map_config():
    """前端高德地图 Key（来自环境变量 / .env）。"""
    key = (os.environ.get("AMAP_JS_KEY") or os.environ.get("AMAP_KEY") or "").strip()
    security = (
        os.environ.get("AMAP_SECURITY_CODE")
        or os.environ.get("AMAP_SECURITY_JS_CODE")
        or ""
    ).strip()
    web_key = (
        os.environ.get("AMAP_WEB_KEY") or os.environ.get("AMAP_JS_KEY") or ""
    ).strip()
    return _ok(
        {
            "provider": "amap",
            "key": key,
            "securityJsCode": security,
            "configured": bool(key),
            "geocodeReady": bool(web_key),
        }
    )


@app.get("/")
def index():
    return FileResponse(FRONTEND / "industry" / "index.html")


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
