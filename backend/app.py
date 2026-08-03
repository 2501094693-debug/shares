"""申万三级行业浏览器 — Flask 后端。"""

from __future__ import annotations

import sys
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from data_service import service
from news_agent import collect_important_news


def _running_under_debugger() -> bool:
    """检测是否在 PyCharm / pydevd 等调试器下运行。

    Flask debug 的 stat reloader 会二次启动进程；若启动命令路径含空格
    （如 D:\\Program Files\\JetBrains\\...），重载时会把路径拆断并报错：
    can't open file 'D:\\\\Program': [Errno 2] No such file or directory
    调试场景下应关闭 use_reloader。
    """
    if "pydevd" in sys.modules:
        return True
    if sys.gettrace() is not None:
        return True
    return False

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"

app = Flask(__name__, static_folder=str(FRONTEND), static_url_path="")
CORS(app)


@app.get("/")
def index():
    return send_from_directory(FRONTEND, "index.html")


@app.get("/company")
@app.get("/company.html")
def company_page():
    return send_from_directory(FRONTEND, "company.html")


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "service": "sw-industry"})


@app.get("/api/industries")
def industries():
    force = request.args.get("refresh") == "1"
    try:
        tree = service.get_tree(force_refresh=force)
        return jsonify({"ok": True, "data": tree})
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.get("/api/search")
def search():
    keyword = request.args.get("q", "")
    try:
        results = service.search(keyword)
        return jsonify({"ok": True, "data": results})
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.get("/api/stocks/search")
def stocks_search():
    name = request.args.get("name", "")
    code = request.args.get("code", "")
    try:
        results = service.search_stocks(name=name, code=code)
        return jsonify(
            {
                "ok": True,
                "data": results,
                "index": service.get_index_status(),
            }
        )
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.get("/api/stocks/index/status")
def stocks_index_status():
    return jsonify({"ok": True, "data": service.get_index_status()})


@app.post("/api/stocks/index/rebuild")
def stocks_index_rebuild():
    force = request.args.get("force") == "1" or request.args.get("refresh") == "1"
    try:
        status = service.start_build_stock_index(force=force)
        return jsonify({"ok": True, "data": status})
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.get("/api/industries/<path:code>/stocks")
def industry_stocks(code: str):
    force = request.args.get("refresh") == "1"
    try:
        data = service.get_constituents(code, force_refresh=force)
        return jsonify({"ok": True, "data": data})
    except KeyError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.get("/api/stocks/profile")
def stocks_profile():
    code = request.args.get("code", "").strip()
    industry = request.args.get("industry", "").strip()
    name = request.args.get("name", "").strip()
    if not code:
        return jsonify({"ok": False, "error": "缺少参数 code"}), 400
    try:
        data = service.get_stock_profile(code, industry_code=industry, name=name)
        return jsonify({"ok": True, "data": data})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.get("/api/stocks/news")
def stocks_news():
    code = request.args.get("code", "").strip()
    name = request.args.get("name", "").strip()
    force = request.args.get("refresh") == "1"
    if not code:
        return jsonify({"ok": False, "error": "缺少参数 code"}), 400
    try:
        data = collect_important_news(code, name, force_refresh=force)
        return jsonify({"ok": True, "data": data})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 500


if __name__ == "__main__":
    try:
        service.get_tree()
        print("行业树加载完成")
    except Exception as exc:  # noqa: BLE001
        print(f"行业树预热失败（首次访问时将重试）: {exc}")

    # 后台构建公司索引，供名称/代码全局搜索
    try:
        service.start_build_stock_index(force=False)
        print("已启动公司索引同步")
    except Exception as exc:  # noqa: BLE001
        print(f"公司索引启动失败: {exc}")

    # 调试器下关闭 reloader，避免 Program Files 路径空格导致二次启动失败
    use_reloader = not _running_under_debugger()
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True,
        use_reloader=use_reloader,
    )
