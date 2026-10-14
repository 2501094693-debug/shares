"""形态筛选 HTTP 路由。"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Body, Query

from analysis.decline.config import DEFAULT_LOOKBACK_DAYS
from analysis.decline.service import service
from analysis.rotation.config import DEFAULT_LOOKBACK_DAYS as ROTATION_LOOKBACK_DAYS
from analysis.rotation.config import MAX_LOOKBACK_DAYS, MIN_LOOKBACK_DAYS
from analysis.rotation.service import service as rotation_service
from analysis.shares.common.config import DEFAULT_LOOKBACK_DAYS as SHARES_LOOKBACK_DAYS
from analysis.shares.common.config import MAX_LOOKBACK_DAYS as SHARES_MAX_LOOKBACK_DAYS
from analysis.shares.common.days import list_trade_days
from analysis.shares.common.service import service as shares_service
from analysis.shares.pattern import normalize_pattern_params
from core.api import err, ok
from core.codes import normalize_code

router = APIRouter()


@router.get("/api/screen/decline")
def get_decline_screen(
    days: int = Query(DEFAULT_LOOKBACK_DAYS, description="近期涨停窗口（交易日）"),
    top: int = Query(30, description="每个交易日前 N 名，0=全部"),
    refresh: str = Query("0", description="1=强制重新分析"),
    workers: int = Query(8, ge=1, le=16, description="并发线程数"),
):
    """阴跌→横盘→涨停：按交易日涨停池分批排名。首次或刷新会后台跑任务。"""
    if days < 1 or days > 30:
        return err("days 须在 1–30 之间", 400)
    if top < 0 or top > 500:
        return err("top 须在 0–500 之间", 400)

    try:
        payload = service.run_or_poll(
            days=days,
            top=top,
            force=refresh == "1",
            workers=workers,
        )
        return ok(payload)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/screen/rotation")
def get_rotation_screen(
    days: int = Query(
        ROTATION_LOOKBACK_DAYS,
        description="回看窗口（交易日，20=近一个月 / 60=近三个月 / 120=近半年 / 245=一年 / 490=两年）",
    ),
    refresh: str = Query("0", description="1=强制重算"),
):
    """申万三级：按日上榜，分为首次/上涨；待涨按距上次上榜最久排序。"""
    if days < MIN_LOOKBACK_DAYS or days > MAX_LOOKBACK_DAYS:
        return err(f"days 须在 {MIN_LOOKBACK_DAYS}–{MAX_LOOKBACK_DAYS} 之间", 400)
    try:
        payload = rotation_service.run_or_poll(days=days, top=0, force=refresh == "1")
        return ok(payload)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.get("/api/screen/shares/days")
def get_shares_trade_days(
    days: int = Query(SHARES_LOOKBACK_DAYS, description="近 N 个交易日（约一个月=22）"),
):
    """近一个月交易日列表 + 可选条件字段说明，供按日勾选筛选条件。"""
    if days < 1 or days > SHARES_MAX_LOOKBACK_DAYS:
        return err(f"days 须在 1–{SHARES_MAX_LOOKBACK_DAYS} 之间", 400)
    try:
        return ok(list_trade_days(days))
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.post("/api/screen/shares")
def post_shares_screen(payload: dict[str, Any] = Body(...)):
    """按多日日线条件筛选股票。

    Body 示例::

        {
          "days": [
            {"date": "2026-09-23", "pct_chg_min": 2, "lower_ratio_min": 0.4},
            {"date": "2026-09-22", "amplitude_min": 3, "amplitude_max": 8}
          ],
          "logic": "and",
          "top": 50,
          "code": "",
          "refresh": "0",
          "workers": 8
        }

    单日可选字段：pct_chg / max_gain / max_drop / body_pct / body_ratio /
    lower_ratio / upper_ratio 的 ``*_min`` / ``*_max``。未填字段表示不限。
    ``logic``：``and`` / ``or`` / ``not``（多日统一组合；若某日带 ``join`` 则改为逐日左结合连接）。
    单日还可设 ``logic``（字段统一与/或/非）、``{field}_join``（与上一已填字段的与/或）、
    ``join``（与上一条件日的与/或）、``not``（本日取反）、``{field}_not``（字段取反）。
    """
    raw_days = payload.get("days") if isinstance(payload, dict) else None
    if not isinstance(raw_days, list) or not raw_days:
        return err("days 须为非空数组", 400)

    try:
        top = int(payload.get("top") if payload.get("top") is not None else 50)
    except (TypeError, ValueError):
        return err("top 无效", 400)
    if top < 0 or top > 500:
        return err("top 须在 0–500 之间", 400)

    try:
        workers = int(payload.get("workers") if payload.get("workers") is not None else 8)
    except (TypeError, ValueError):
        return err("workers 无效", 400)
    if workers < 1 or workers > 16:
        return err("workers 须在 1–16 之间", 400)

    logic = str(payload.get("logic") or "and").strip().lower()
    if logic not in ("and", "or", "not", "nor"):
        return err("logic 须为 and、or 或 not", 400)
    if logic == "nor":
        logic = "not"

    refresh = str(payload.get("refresh") or "0").strip()
    code = normalize_code(str(payload.get("code") or ""))

    try:
        result = shares_service.run_or_poll(
            day_specs=raw_days,
            logic=logic,
            top=top,
            code=code,
            force=refresh == "1",
            workers=workers,
        )
        if result.get("status") == "error" and "data" not in result:
            return err(str(result.get("error") or "筛选失败"), 400)
        return ok(result)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.post("/api/screen/shares/pattern")
def post_shares_pattern(payload: dict[str, Any] = Body(...)):
    """按内联 JSON 形态方案筛选。

    Body 示例::

        {
          "scheme": {
            "id": "my_scheme",
            "logic": "or",
            "groups": [ ... ]
          },
          "top": 50
        }

    也可直接把 groups 放在 body 顶层。
    """
    if not isinstance(payload, dict):
        return err("body 须为对象", 400)

    has_inline = isinstance(payload.get("scheme"), dict) or (
        isinstance(payload.get("groups"), list) and bool(payload.get("groups"))
    )
    if not has_inline:
        return err("须提供 scheme 对象或非空 groups 数组", 400)

    try:
        top = int(payload.get("top") if payload.get("top") is not None else 50)
    except (TypeError, ValueError):
        return err("top 无效", 400)
    if top < 0 or top > 500:
        return err("top 须在 0–500 之间", 400)

    try:
        workers = int(payload.get("workers") if payload.get("workers") is not None else 8)
    except (TypeError, ValueError):
        return err("workers 无效", 400)
    if workers < 1 or workers > 16:
        return err("workers 须在 1–16 之间", 400)

    refresh = str(payload.get("refresh") or "0").strip()
    code = normalize_code(str(payload.get("code") or ""))
    try:
        params = normalize_pattern_params(payload)
    except ValueError as exc:
        return err(str(exc), 400)

    try:
        from analysis.shares.pattern import load_pattern_scheme, scheme_has_rules

        scheme = load_pattern_scheme(params)
        if not scheme_has_rules(scheme):
            return err("方案无有效条件日", 400)
    except Exception as exc:  # noqa: BLE001
        return err(f"方案无效: {exc}", 400)

    try:
        result = shares_service.run_or_poll_pattern(
            params=params,
            top=top,
            code=code,
            force=refresh == "1",
            workers=workers,
        )
        if result.get("status") == "error" and "data" not in result:
            return err(str(result.get("error") or "筛选失败"), 400)
        return ok(result)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.post("/api/screen/shares/compare")
def post_shares_compare(payload: dict[str, Any] = Body(...)):
    """按跨日对比方案筛选：比较前后若干交易日的日线指标。

    Body 示例::

        {
          "scheme": {
            "id": "settle_compare",
            "name": "对比趋稳",
            "logic": "and",
            "days": [{"offset": 0, "pct_chg_min": -1.2, "pct_chg_max": 1.2}],
            "comps": [
              {
                "field": "body_abs_pct",
                "offsets": [4, 3, 2, 1, 0],
                "trend": "down",
                "min_pairs": 3
              },
              {"field": "vol_ratio", "left": 0, "right": 3, "op": "lt"}
            ]
          },
          "top": 50
        }

    也可把 comps / days 放在 body 顶层。
    comps 支持：
    - 两两对比：left/right（offset）+ op（lt/le/gt/ge/eq）+ 可选 ratio_*/delta_*
    - 序列趋势：offsets + trend（down/up/flat）+ 可选 min_pairs / strict
    字段见 /api/screen/shares/days 的 compare_fields。
    """
    if not isinstance(payload, dict):
        return err("body 须为对象", 400)

    has_inline = (
        isinstance(payload.get("scheme"), dict)
        or (isinstance(payload.get("comps"), list) and bool(payload.get("comps")))
        or (isinstance(payload.get("days"), list) and bool(payload.get("days")))
    )
    if not has_inline:
        return err("须提供 scheme 对象，或非空 comps / days", 400)

    try:
        top = int(payload.get("top") if payload.get("top") is not None else 50)
    except (TypeError, ValueError):
        return err("top 无效", 400)
    if top < 0 or top > 500:
        return err("top 须在 0–500 之间", 400)

    try:
        workers = int(payload.get("workers") if payload.get("workers") is not None else 8)
    except (TypeError, ValueError):
        return err("workers 无效", 400)
    if workers < 1 or workers > 16:
        return err("workers 须在 1–16 之间", 400)

    refresh = str(payload.get("refresh") or "0").strip()
    code = normalize_code(str(payload.get("code") or ""))

    try:
        from analysis.shares.compare import (
            compare_has_rules,
            load_compare_scheme,
            normalize_compare_params,
        )

        params = normalize_compare_params(payload)
        scheme = load_compare_scheme(params)
        if not compare_has_rules(scheme):
            return err("方案无有效对比或绝对条件", 400)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(f"方案无效: {exc}", 400)

    try:
        result = shares_service.run_or_poll_compare(
            params=params,
            top=top,
            code=code,
            force=refresh == "1",
            workers=workers,
        )
        if result.get("status") == "error" and "data" not in result:
            return err(str(result.get("error") or "筛选失败"), 400)
        return ok(result)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.post("/api/screen/shares/pullback")
def post_shares_pullback(payload: dict[str, Any] = Body(...)):
    """涨停回踩：N天内有涨停 + 贴近窗口低点/涨停开盘。Body: {window, mode, dist_low_max, dist_open_max, top}"""
    if not isinstance(payload, dict):
        return err("body 须为对象", 400)
    try:
        top = int(payload.get("top") if payload.get("top") is not None else 50)
    except (TypeError, ValueError):
        return err("top 无效", 400)
    try:
        workers = int(payload.get("workers") if payload.get("workers") is not None else 8)
    except (TypeError, ValueError):
        workers = 8
    refresh = str(payload.get("refresh") or "0").strip()
    code = normalize_code(str(payload.get("code") or ""))
    try:
        result = shares_service.run_or_poll_pullback(params=payload, top=top, code=code, force=refresh == "1", workers=workers)
        if result.get("status") == "error" and "data" not in result:
            return err(str(result.get("error") or "筛选失败"), 400)
        return ok(result)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)


@router.post("/api/screen/shares/scheme")
def post_shares_scheme(payload: dict[str, Any] = Body(...)):
    """统一 AST 组合筛选：一次扫盘同时评估 day / group / comp。

    Body 示例（显式 nodes）::

        {
          "scheme": {
            "id": "shrink_then_absorb",
            "logic": "and",
            "nodes": [
              {"kind": "comp", "field": "body_abs_pct",
               "offsets": [4, 3, 2, 1, 0], "trend": "down", "min_pairs": 3},
              {"kind": "group", "logic": "or", "nodes": [
                {"kind": "day", "offset": 0, "lower_ratio_min": 0.35, "lower_ge_body": true},
                {"kind": "group", "min_hits": 2, "nodes": [
                  {"kind": "day", "offset": 0, "body_abs_pct_max": 1.2},
                  {"kind": "day", "offset": 1, "body_abs_pct_max": 1.2},
                  {"kind": "day", "offset": 2, "body_abs_pct_max": 1.2}
                ]}
              ]}
            ]
          },
          "top": 50
        }

    也可把三种旧草稿 AND 组合::

        {
          "logic": "and",
          "screen": {"days": [{"date": "2026-09-23", "pct_chg_min": 2}], "logic": "and"},
          "pattern": {"logic": "or", "groups": [...]},
          "compare": {"comps": [...], "days": [...], "logic": "and"},
          "top": 50
        }

    节点 kind：``day`` / ``comp`` / ``group``；组可用 ``min_hits`` 或 and/or/not。
    """
    if not isinstance(payload, dict):
        return err("body 须为对象", 400)

    has_inline = (
        isinstance(payload.get("scheme"), dict)
        or (isinstance(payload.get("nodes"), list) and bool(payload.get("nodes")))
        or payload.get("screen") is not None
        or payload.get("screen_days") is not None
        or payload.get("pattern") is not None
        or payload.get("pattern_scheme") is not None
        or payload.get("compare") is not None
        or payload.get("compare_scheme") is not None
    )
    if not has_inline:
        return err("须提供 scheme / nodes，或 screen / pattern / compare 草稿", 400)

    try:
        top = int(payload.get("top") if payload.get("top") is not None else 50)
    except (TypeError, ValueError):
        return err("top 无效", 400)
    if top < 0 or top > 500:
        return err("top 须在 0–500 之间", 400)

    try:
        workers = int(payload.get("workers") if payload.get("workers") is not None else 8)
    except (TypeError, ValueError):
        return err("workers 无效", 400)
    if workers < 1 or workers > 16:
        return err("workers 须在 1–16 之间", 400)

    refresh = str(payload.get("refresh") or "0").strip()
    code = normalize_code(str(payload.get("code") or ""))

    try:
        from analysis.shares.compose import (
            load_compose_tree,
            normalize_compose_params,
            tree_has_rules,
        )

        params = normalize_compose_params(payload)
        tree = load_compose_tree(params)
        if not tree_has_rules(tree):
            return err("方案无有效节点", 400)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return err(f"方案无效: {exc}", 400)

    try:
        result = shares_service.run_or_poll_compose(
            params=params,
            top=top,
            code=code,
            force=refresh == "1",
            workers=workers,
        )
        if result.get("status") == "error" and "data" not in result:
            return err(str(result.get("error") or "筛选失败"), 400)
        return ok(result)
    except Exception as exc:  # noqa: BLE001
        return err(str(exc), 500)
@router.post("/api/analysis/select/screen")
def post_select_screen(payload: dict = Body(...)):
    """精选股票分析：按 compare/price/jetton 参数批量分析并按结果筛选。"""
    if not isinstance(payload, dict):
        return err("body error", 400)
    symbols = payload.get("symbols")
    if not isinstance(symbols, list) or not symbols:
        return err("symbols is required", 400)
    if len(symbols) > 500:
        return err("symbols max 500", 400)
    try:
        from analysis.select.params import SelectParams
        from analysis.select.screener import screen_stocks
        raw = payload.get("params") if isinstance(payload.get("params"), dict) else payload
        params = SelectParams.from_dict(raw)
        result = screen_stocks([str(s) for s in symbols], params)
        return ok(result)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:
        return err(str(exc), 500)


@router.post("/api/analysis/select/analyze")
def post_select_analyze(payload: dict = Body(...)):
    """精选股票分析：单只股票跑启用的分析并返回指标。"""
    if not isinstance(payload, dict):
        return err("body error", 400)
    symbol = str(payload.get("symbol") or payload.get("code") or "").strip()
    if not symbol:
        return err("symbol is required", 400)
    try:
        from analysis.select.params import SelectParams
        from analysis.select.screener import analyze_one
        raw = payload.get("params") if isinstance(payload.get("params"), dict) else payload
        params = SelectParams.from_dict(raw)
        return ok(analyze_one(symbol, params))
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:
        return err(str(exc), 500)
@router.get("/api/analysis/chip")
def get_chip_analysis(
    company: str = Query("", description="公司名称或代码"),
    start: str = Query("", description="区间开始 YYYY-MM-DD"),
    end: str = Query("", description="区间结束 YYYY-MM-DD"),
    target: str = Query("", description="目标日 YYYY-MM-DD"),
    order: str = Query("desc", description="asc 或 desc"),
):
    """筹码分析（价格位置）：目标日 OHLC 在区间同类价格中的排名与百分比。"""
    from datetime import date, timedelta
    from analysis.select.price.service import price_position
    m = re.search(r"(\d{6})", company or "")
    symbol = m.group(1) if m else (company or "").strip()
    if not symbol:
        return err("company symbol is required", 400)
    today = date.today().isoformat()
    if not end:
        end = today
    if not start:
        try:
            end_d = date.fromisoformat(end[:10])
        except ValueError:
            end_d = date.today()
        start = (end_d - timedelta(days=365)).isoformat()
    if not target:
        target = end
    try:
        result = price_position(symbol, start, end, target, order or "desc")
        return ok(result)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:
        return err(str(exc), 500)
@router.get("/api/analysis/compare")
def get_compare_analysis(
    company: str = Query("", description="公司名称或代码"),
    index: str = Query("SH000001", description="对比指数代码"),
    beg: str = Query("", description="区间开始 YYYY-MM-DD"),
    end: str = Query("", description="区间结束 YYYY-MM-DD"),
):
    """对比分析：个股相对指数的 OHLC 四图偏离度。"""
    from datetime import date, timedelta
    from analysis.select.compare.stock_vs_index import compare_stock_vs_index
    m = re.search(r"(\d{6})", company or "")
    symbol = m.group(1) if m else (company or "").strip()
    if not symbol:
        return err("company symbol is required", 400)
    index_code = (index or "SH000001").strip()
    today = date.today().isoformat()
    if not end:
        end = today
    if not beg:
        try:
            end_d = date.fromisoformat(end[:10])
        except ValueError:
            end_d = date.today()
        beg = (end_d - timedelta(days=365)).isoformat()
    try:
        result = compare_stock_vs_index(symbol, index_code, beg[:10], end[:10])
        return ok(result)
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if "Connection aborted" in msg or "RemoteDisconnected" in msg or "ConnectionError" in type(exc).__name__:
            return err("行情接口连接中断（东财限流/抖动），请等待10秒后点“重新计算”重试", 503)
        return err(msg, 500)
@router.post("/api/analysis/select/price-screen")
def post_price_screen(payload: dict = Body(...)):
    """股票分析（价格位置）：默认全市场扫描，按 price 参数批量分析并按分位筛选。"""
    if not isinstance(payload, dict):
        return err("body error", 400)
    symbols = payload.get("symbols")
    if symbols is None:
        try:
            from market.shares.service import service as shares_service
            data = shares_service.list()
            symbols = [str((it or {}).get("code") or "") for it in (data.get("items") or [])]
            symbols = [s for s in symbols if s.strip()]
        except Exception as exc:
            return err(f"全市场列表获取失败: {exc}", 500)
    if not isinstance(symbols, list) or not symbols:
        return err("symbols is required", 400)
    if len(symbols) > 6000:
        return err("symbols max 6000", 400)
    start = str(payload.get("start") or "").strip()
    end = str(payload.get("end") or "").strip()
    target = str(payload.get("target") or "").strip()
    order = str(payload.get("order") or "desc").strip().lower()
    filters = payload.get("filters") if isinstance(payload.get("filters"), dict) else {}
    pct_min = filters.get("percent_min") if isinstance(filters.get("percent_min"), dict) else {}
    pct_max = filters.get("percent_max") if isinstance(filters.get("percent_max"), dict) else {}
    try:
        workers = max(1, min(int(payload.get("max_workers", 32)), 64))
    except (TypeError, ValueError):
        return err("max_workers invalid", 400)
    try:
        from concurrent.futures import ThreadPoolExecutor
        from analysis.select.price.service import FIELDS, price_position

        def _one(symbol: str) -> dict:
            symbol = str(symbol).strip()
            try:
                r = price_position(symbol, start, end, target, order)
            except Exception as exc:
                return {"symbol": symbol, "pass": False, "reasons": [str(exc)], "metrics": {}}
            res = r.get("result") or {}
            metrics = {}
            for k in FIELDS:
                if isinstance(res.get(k), dict):
                    metrics[k] = {"percent": res[k].get("percent"), "rank": res[k].get("rank"),
                                  "total": res[k].get("total"), "value": res[k].get("value")}
            reasons = []
            for k in FIELDS:
                v = (metrics.get(k) or {}).get("percent")
                if v is None:
                    continue
                if k in pct_min and v < float(pct_min[k]):
                    reasons.append(f"{k}{v}低于{pct_min[k]}")
                if k in pct_max and v > float(pct_max[k]):
                    reasons.append(f"{k}{v}高于{pct_max[k]}")
            return {"symbol": symbol, "pass": not reasons, "reasons": reasons,
                    "metrics": metrics, "target": r.get("target"), "N": r.get("N")}

        with ThreadPoolExecutor(max_workers=workers) as pool:
            rows = list(pool.map(_one, [str(s) for s in symbols]))
        passed = sorted([r for r in rows if r.get("pass")],
                        key=lambda r: ((r.get("metrics") or {}).get("close") or {}).get("percent") or 0,
                        reverse=True)
        failed = [r for r in rows if not r.get("pass")]
        return ok({"params": {"start": start, "end": end, "target": target, "order": order,
                              "filters": {"percent_min": pct_min, "percent_max": pct_max}},
                   "total": len(rows), "passed": passed, "failed": failed,
                   "passed_symbols": [r["symbol"] for r in passed]})
    except ValueError as exc:
        return err(str(exc), 400)
    except Exception as exc:
        return err(str(exc), 500)
@router.post("/api/analysis/select/price-stream")
def post_price_stream(payload: dict = Body(...)):
    """股票分析流式扫描：NDJSON 逐只推送，符合条件的直接展示。"""
    import json
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from fastapi.responses import StreamingResponse
    if not isinstance(payload, dict):
        return err("body error", 400)
    symbols = payload.get("symbols")
    names: dict[str, str] = {}
    if symbols is None:
        try:
            from market.shares.service import service as shares_service
            data = shares_service.list()
            items = data.get("items") or []
            symbols = []
            for it in items:
                code = str((it or {}).get("code") or "").strip()
                if code:
                    symbols.append(code)
                    names[code] = str((it or {}).get("name") or "")
        except Exception as exc:
            return err(f"market list failed: {exc}", 500)
    if not isinstance(symbols, list) or not symbols:
        return err("symbols is required", 400)
    symbols = [str(s).strip() for s in symbols if str(s).strip()][:6000]
    skip = payload.get("skip")
    if isinstance(skip, list) and skip:
        skip_set = {str(s).strip() for s in skip if str(s).strip()}
        if skip_set:
            symbols = [s for s in symbols if s not in skip_set]
    start = str(payload.get("start") or "").strip()
    end = str(payload.get("end") or "").strip()
    target = str(payload.get("target") or "").strip()
    order = str(payload.get("order") or "desc").strip().lower()
    filters = payload.get("filters") if isinstance(payload.get("filters"), dict) else {}
    pct_min = filters.get("percent_min") if isinstance(filters.get("percent_min"), dict) else {}
    pct_max = filters.get("percent_max") if isinstance(filters.get("percent_max"), dict) else {}
    try:
        workers = max(1, min(int(payload.get("max_workers", 32)), 64))
    except (TypeError, ValueError):
        return err("max_workers invalid", 400)

    def _one(symbol: str) -> dict:
        from analysis.select.price.service import FIELDS, price_position
        try:
            r = price_position(symbol, start, end, target, order)
        except Exception as exc:
            return {"symbol": symbol, "name": names.get(symbol, ""), "pass": False,
                    "reasons": [str(exc)], "metrics": {}}
        res = r.get("result") or {}
        metrics = {}
        for k in FIELDS:
            if isinstance(res.get(k), dict):
                metrics[k] = {"percent": res[k].get("percent"), "rank": res[k].get("rank"),
                              "total": res[k].get("total"), "value": res[k].get("value")}
        reasons = []
        for k in FIELDS:
            v = (metrics.get(k) or {}).get("percent")
            if v is None:
                continue
            if k in pct_min and v < float(pct_min[k]):
                reasons.append(f"{k}{v}低于{pct_min[k]}")
            if k in pct_max and v > float(pct_max[k]):
                reasons.append(f"{k}{v}高于{pct_max[k]}")
        return {"symbol": symbol, "name": names.get(symbol, ""), "pass": not reasons,
                "reasons": reasons, "metrics": metrics, "target": r.get("target"), "N": r.get("N")}

    def _gen():
        yield json.dumps({"type": "info", "total": len(symbols),
                          "params": {"start": start, "end": end, "target": target, "order": order}},
                         ensure_ascii=False) + "\n"
        done = 0
        passed = 0
        try:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                # 分批提交：边算边吐，避免一次性堆积数千 future
                it = iter(symbols)
                pending = set()
                BATCH = max(workers * 2, 64)

                def _fill():
                    for _ in range(BATCH - len(pending)):
                        try:
                            s = next(it)
                        except StopIteration:
                            break
                        pending.add(pool.submit(_one, s))

                _fill()
                while pending:
                    for fut in as_completed(list(pending)):
                        pending.discard(fut)
                        try:
                            row = fut.result()
                        except Exception as exc:
                            row = {"symbol": "", "name": "", "pass": False,
                                   "reasons": [str(exc)], "metrics": {}}
                        done += 1
                        if row.get("pass"):
                            passed += 1
                        yield json.dumps({"type": "item", "done": done, "passed": passed,
                                          "total": len(symbols), "row": row}, ensure_ascii=False) + "\n"
                        _fill()
                        break
        except GeneratorExit:
            return
        yield json.dumps({"type": "done", "done": done, "passed": passed,
                          "total": len(symbols)}, ensure_ascii=False) + "\n"

    return StreamingResponse(_gen(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
