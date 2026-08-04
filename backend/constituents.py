"""三级行业成分股：远程拉取、磁盘缓存、字段规范化。"""

from __future__ import annotations

import json
import time
from typing import Any, Callable

import pandas as pd

from cons_fetcher import fetch_third_cons
from paths import CONS_TTL, cons_cache_path, ensure_cache_dirs

GetL3Meta = Callable[[str], dict[str, Any] | None]
OnStocksUpdated = Callable[[dict[str, Any], list[dict[str, Any]]], None]


def _cell(row: Any, key: str) -> str:
    val = row.get(key, "")
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    text = str(val).strip()
    return "" if text in {"nan", "None", "—", "-", "<NA>"} else text


def normalize_constituent_row(row: Any, meta: dict[str, Any]) -> dict[str, Any]:
    stock_code = _cell(row, "股票代码")
    short_code = stock_code.split(".")[0] if stock_code else ""
    return {
        "code": short_code,
        "full_code": stock_code,
        "name": _cell(row, "股票简称"),
        "l1": meta.get("l1_name", ""),
        "l2": meta.get("l2_name", ""),
        "l3": _cell(row, "申万3级") or meta.get("name", ""),
        "include_date": _cell(row, "纳入时间"),
        "price": _cell(row, "价格"),
        "pe": _cell(row, "市盈率"),
        "pe_ttm": _cell(row, "市盈率ttm"),
        "pb": _cell(row, "市净率"),
        "roe": _cell(row, "ROE"),
        "dividend_yield": _cell(row, "股息率"),
        "market_cap": _cell(row, "市值"),
        "change_1d": _cell(row, "近1日涨幅"),
        "change_5d": _cell(row, "近5日涨幅"),
        "change_ytd": _cell(row, "今年以来涨幅"),
        "profit_growth": _cell(row, "净利润增速"),
        "revenue_growth": _cell(row, "营收增速"),
    }


def read_cons_cache(l3_code: str) -> dict[str, Any] | None:
    path = cons_cache_path(l3_code)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def write_cons_cache(l3_code: str, payload: dict[str, Any]) -> None:
    ensure_cache_dirs()
    cons_cache_path(l3_code).write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


def iter_cons_cache_files():
    from paths import CONS_CACHE_DIR

    ensure_cache_dirs()
    return CONS_CACHE_DIR.glob("*.json")


def build_code_lookup(stocks: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """短码 / 完整码 → 成分股记录。"""
    lookup: dict[str, dict[str, Any]] = {}
    for s in stocks:
        full = str(s.get("full_code") or "").strip().lower()
        short = str(s.get("code") or "").strip().lower()
        if full:
            lookup[full] = s
        if short:
            lookup[short] = s
    return lookup


class ConstituentsRepo:
    """按三级行业获取成分股（缓存优先）。"""

    def __init__(
        self,
        get_l3_meta: GetL3Meta,
        on_updated: OnStocksUpdated | None = None,
    ) -> None:
        self._get_l3_meta = get_l3_meta
        self._on_updated = on_updated

    def get(
        self,
        code: str,
        force_refresh: bool = False,
        notify_index: bool = True,
    ) -> dict[str, Any]:
        code = code.strip()
        meta = self._get_l3_meta(code)
        if meta is None:
            raise KeyError(f"未找到三级行业: {code}")

        if not force_refresh:
            cached = read_cons_cache(code)
            if cached and time.time() - cached.get("fetched_at", 0) < CONS_TTL:
                if notify_index and self._on_updated:
                    self._on_updated(meta, cached.get("stocks") or [])
                return cached

        df = fetch_third_cons(code)
        stocks = [normalize_constituent_row(row, meta) for _, row in df.iterrows()]
        payload = {
            "industry": meta,
            "count": len(stocks),
            "stocks": stocks,
            "fetched_at": time.time(),
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        write_cons_cache(code, payload)
        if notify_index and self._on_updated:
            self._on_updated(meta, stocks)
        return payload

    def find_stock_in_industry(
        self, industry_code: str, code: str
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        """在指定行业成分股中查找股票，返回 (stock, industry_meta)。"""
        try:
            data = self.get(industry_code, force_refresh=False, notify_index=True)
        except KeyError:
            return None, None
        code_l = code.strip().lower()
        lookup = build_code_lookup(data.get("stocks") or [])
        hit = lookup.get(code_l)
        if hit is None:
            # 兼容「代码作为完整码子串」的宽松匹配
            for s in data.get("stocks") or []:
                full = str(s.get("full_code") or "").lower()
                if code_l == str(s.get("code") or "").lower() or code_l in full:
                    hit = s
                    break
        return (dict(hit) if hit else None), (data.get("industry") or None)
