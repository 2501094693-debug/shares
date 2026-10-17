"""同行比对的样本圈定：解析申万三级行业、取成分股、剔除不可比样本、并发拉 F10。

不依赖申万行业树「全量扫描已完成」：成分股走 ``get_constituents``（自带 6h 缓存）；
行业归属优先用目标公司的反查命中，其次用显式传入的行业代码。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from market.industry.service import service as industry

# 名称里出现这些标记的股票不进对比样本
_EXCLUDE_NAME_MARKERS = ("ST", "*ST", "退", "退市")
# 同时命中的 F10 并发上限
_FETCH_WORKERS = 8


def _clean_code(code: str) -> str:
    return str(code or "").strip()


def _is_excluded_name(name: str) -> str:
    """命中剔除规则返回原因，否则空串。"""
    text = str(name or "")
    for marker in _EXCLUDE_NAME_MARKERS:
        if marker in text:
            return f"名称含「{marker}」"
    return ""


def resolve_industry(code: str = "", industry_code: str = "") -> dict[str, Any]:
    """确定行业：优先显式 ``industry_code``；否则用目标公司反查申万三级归属。

    返回 ``{l3_code, l3_name, l1_name, l2_name}``；解析失败抛 ``ValueError``。
    """
    code = _clean_code(code)
    industry_code = _clean_code(industry_code)

    if industry_code:
        meta = industry.tree.get_l3_meta(industry_code)
        if meta is None:
            raise ValueError(f"未找到申万三级行业: {industry_code}")
        return {
            "l3_code": industry_code,
            "l3_name": meta.get("name") or "",
            "l1_name": meta.get("l1_name") or "",
            "l2_name": meta.get("l2_name") or "",
        }

    if not code:
        raise ValueError("缺少参数 code 或 industry")

    industry.stocks.ensure_populated()
    hit = industry.stocks.get_by_code(code)
    l3_code = _clean_code((hit or {}).get("l3_code"))
    if not l3_code:
        raise ValueError(f"未能从申万行业索引反查到 {code} 的三级行业归属，请显式传入 industry")

    meta = industry.tree.get_l3_meta(l3_code) or {}
    return {
        "l3_code": l3_code,
        "l3_name": (hit or {}).get("l3_name") or meta.get("name") or "",
        "l1_name": (hit or {}).get("l1_name") or meta.get("l1_name") or "",
        "l2_name": (hit or {}).get("l2_name") or meta.get("l2_name") or "",
    }


def _constituents(l3_code: str, force_refresh: bool = False) -> list[dict[str, Any]]:
    try:
        pack = industry.stocks.get_constituents(l3_code, force_refresh=force_refresh)
    except KeyError as exc:
        raise ValueError(str(exc)) from exc
    return list(pack.get("stocks") or [])


def _market_cap_value(stock: dict[str, Any]) -> float:
    """市值字段是字符串（可能带亿/万），粗略转 float 用于排序。"""
    raw = str(stock.get("market_cap") or "").strip()
    if not raw:
        return 0.0
    mult = 1.0
    if "亿" in raw:
        mult = 1e8
    elif "万" in raw:
        mult = 1e4
    text = raw.replace("亿", "").replace("万", "").replace(",", "").strip()
    try:
        return float(text) * mult
    except ValueError:
        return 0.0


def build_universe(
    l3_code: str,
    *,
    target_code: str = "",
    peers: int = 0,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """圈定对比样本。

    ``peers<=0`` 取全部；否则按市值降序取 Top N，目标公司始终保留。
    剔除 ST/退市类；重复代码去重。
    """
    target_code = _clean_code(target_code)
    rows = _constituents(l3_code, force_refresh=force_refresh)

    seen: set[str] = set()
    usable: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    for row in rows:
        code = _clean_code(row.get("code"))
        if not code or code in seen:
            continue
        seen.add(code)
        reason = _is_excluded_name(row.get("name") or "")
        if reason:
            excluded.append({"code": code, "name": row.get("name") or "", "reason": reason})
            continue
        usable.append(
            {
                "code": code,
                "name": row.get("name") or code,
                "full_code": row.get("full_code") or "",
                "market_cap": _market_cap_value(row),
            }
        )

    if peers and peers > 0 and len(usable) > peers:
        ranked = sorted(usable, key=lambda s: s["market_cap"], reverse=True)
        keep: list[dict[str, Any]] = ranked[:peers]
        keep_codes = {s["code"] for s in keep}
        if target_code and target_code not in keep_codes:
            target_row = next((s for s in usable if s["code"] == target_code), None)
            if target_row is not None:
                keep.append(target_row)
        dropped = [s for s in usable if s["code"] not in {k["code"] for k in keep}]
        for s in dropped:
            excluded.append({"code": s["code"], "name": s["name"], "reason": f"超出前 {peers} 名"})
        usable = keep

    return {
        "total": len(rows),
        "used": len(usable),
        "stocks": usable,
        "excluded": excluded,
    }


def fetch_series(
    stocks: list[dict[str, Any]],
    report_type: str,
    *,
    force: bool = False,
) -> dict[str, list[dict[str, Any]]]:
    """并发拉每家 F10 并裁成同口径序列（最新 2 期）。

    返回 ``{code: series}``；拉取失败的公司值为空列表，由调用方判定剔除。
    """
    from company.analysis.financialreport._common import select_series
    from company.news.financialreport.fetcher import get_financial_report

    def _one(stock: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
        code = stock["code"]
        try:
            pack = get_financial_report(code, scope="all", limit=8, force=force)
            merged = pack.get("merged") or []
            return code, select_series(merged, report_type, limit=2)
        except Exception:  # noqa: BLE001
            return code, []

    out: dict[str, list[dict[str, Any]]] = {}
    if not stocks:
        return out
    with ThreadPoolExecutor(max_workers=_FETCH_WORKERS) as pool:
        for code, series in pool.map(_one, stocks):
            out[code] = series
    return out
