"""龙虎榜查询：按日汇总买卖方，或按代码查历史上榜。"""

from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any

from core.cache import TtlCache
from core.codes import normalize_code
from core.paths import LIST_CACHE_DIR, ensure_cache_dirs
from industry.service import service as industry_service
from market.steep.calendar import recent_trade_dates

from .em_lhb import fetch_details, fetch_seats, ymd, ymd_dash

_MEM_TTL = 90
_TODAY_DISK_TTL = 3 * 60
_HIST_DISK_TTL = 7 * 24 * 60 * 60
_STOCK_DISK_TTL = 10 * 60
_CACHE_VERSION = 1


def _today() -> str:
    return datetime.now().strftime("%Y%m%d")


def _is_today(date_raw: str) -> bool:
    return date_raw == _today()


def _disk_path(kind: str, key: str) -> Any:
    ensure_cache_dirs()
    return LIST_CACHE_DIR / f"{kind}_{key}.json"


def _load_disk(kind: str, key: str, ttl: float) -> dict[str, Any] | None:
    path = _disk_path(kind, key)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if int(payload.get("version") or 0) != _CACHE_VERSION:
        return None
    cached_at = float(payload.get("cached_at") or 0)
    if time.time() - cached_at > ttl:
        return None
    data = payload.get("data")
    return data if isinstance(data, dict) else None


def _save_disk(kind: str, key: str, data: dict[str, Any]) -> None:
    path = _disk_path(kind, key)
    path.write_text(
        json.dumps(
            {"version": _CACHE_VERSION, "cached_at": time.time(), "data": data},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _listing_key(row: dict[str, Any]) -> tuple[str, str, str]:
    trade_id = str(row.get("trade_id") or "").strip()
    reason = str(row.get("reason") or "").strip()
    return (
        str(row.get("code") or ""),
        str(row.get("date") or ""),
        trade_id or reason,
    )


def _copy_quote(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": row["code"],
        "name": row.get("name") or "",
        "date": row.get("date") or "",
        "date_raw": row.get("date_raw") or "",
        "market": row.get("market") or "",
        "close": row.get("close"),
        "change_pct": row.get("change_pct"),
        "turnover": row.get("turnover"),
        "free_cap": row.get("free_cap"),
    }


def _listing_from_detail(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "reason": row.get("reason") or "",
        "explain": row.get("explain") or "",
        "trade_id": row.get("trade_id") or "",
        "net_amt": row.get("net_amt"),
        "buy_amt": row.get("buy_amt"),
        "sell_amt": row.get("sell_amt"),
        "deal_amt": row.get("deal_amt"),
        "accum_amt": row.get("accum_amt"),
        "net_ratio": row.get("net_ratio"),
        "deal_ratio": row.get("deal_ratio"),
        "d1": row.get("d1"),
        "d2": row.get("d2"),
        "d5": row.get("d5"),
        "d10": row.get("d10"),
        "buyers": [],
        "sellers": [],
    }


def _public_seat(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "dept": row.get("dept") or "",
        "dept_code": row.get("dept_code") or "",
        "dept_type": row.get("dept_type") or "",
        "buy": row.get("buy"),
        "sell": row.get("sell"),
        "net": row.get("net"),
        "buy_ratio": row.get("buy_ratio"),
        "sell_ratio": row.get("sell_ratio"),
        "rise_prob_3d": row.get("rise_prob_3d"),
        "appear_3d": row.get("appear_3d") or 0,
    }


def _sort_seats(rows: list[dict[str, Any]], side: str) -> list[dict[str, Any]]:
    key = "buy" if side == "buy" else "sell"

    def _amt(item: dict[str, Any]) -> float:
        val = item.get(key)
        return float(val) if isinstance(val, (int, float)) else -1.0

    ranked = sorted(rows, key=_amt, reverse=True)
    out = []
    for idx, item in enumerate(ranked, start=1):
        seat = _public_seat(item)
        seat["rank"] = idx
        out.append(seat)
    return out


def _amt(row: dict[str, Any], field: str = "net_amt") -> float:
    val = row.get(field)
    return float(val) if isinstance(val, (int, float)) else 0.0


def assemble(
    details: list[dict[str, Any]],
    buyers: list[dict[str, Any]],
    sellers: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """同一股票同一天的多条上榜原因收成一条，席位挂到对应原因下。"""
    listings: dict[tuple[str, str, str], dict[str, Any]] = {}
    stocks: dict[tuple[str, str], dict[str, Any]] = {}

    for row in details:
        lkey = _listing_key(row)
        skey = (row["code"], row["date"])
        listing = listings.get(lkey)
        if listing is None:
            listing = _listing_from_detail(row)
            listings[lkey] = listing
        stock = stocks.get(skey)
        if stock is None:
            stock = {**_copy_quote(row), "listings": []}
            stocks[skey] = stock
        elif not stock.get("name") and row.get("name"):
            stock["name"] = row["name"]
        if listing not in stock["listings"]:
            stock["listings"].append(listing)

    for side, rows in (("buyers", buyers), ("sellers", sellers)):
        for row in rows:
            listing = listings.get(_listing_key(row))
            if listing is None:
                continue
            listing[side].append(row)

    items = []
    for stock in stocks.values():
        for listing in stock["listings"]:
            listing["buyers"] = _sort_seats(listing["buyers"], "buy")
            listing["sellers"] = _sort_seats(listing["sellers"], "sell")
        stock["listings"].sort(key=lambda item: _amt(item), reverse=True)
        primary = stock["listings"][0] if stock["listings"] else {}
        stock["net_amt"] = primary.get("net_amt")
        stock["buy_amt"] = primary.get("buy_amt")
        stock["sell_amt"] = primary.get("sell_amt")
        stock["deal_amt"] = primary.get("deal_amt")
        stock["reasons"] = [item.get("reason") or "" for item in stock["listings"] if item.get("reason")]
        items.append(stock)

    items.sort(key=lambda item: (_amt(item), item.get("code") or ""), reverse=True)
    return items


def _sw_map() -> dict[str, dict[str, str]]:
    industry_service.stocks.ensure_populated()
    out: dict[str, dict[str, str]] = {}
    for stock in industry_service.stocks.all_stocks():
        code = str(stock.get("code") or "").strip()
        if not code or code in out:
            continue
        out[code] = {
            "l1_name": str(stock.get("l1_name") or "").strip(),
            "l2_name": str(stock.get("l2_name") or "").strip(),
            "l3_name": str(stock.get("l3_name") or "").strip(),
            "l3_code": str(stock.get("l3_code") or "").strip(),
        }
    return out


def _attach_sw(items: list[dict[str, Any]]) -> None:
    mapping = _sw_map()
    empty = {"l1_name": "", "l2_name": "", "l3_name": "", "l3_code": ""}
    for row in items:
        meta = mapping.get(str(row.get("code") or "").strip()) or empty
        row["l1_name"] = meta["l1_name"]
        row["l2_name"] = meta["l2_name"]
        row["l3_name"] = meta["l3_name"]
        row["l3_code"] = meta["l3_code"]


def _pack_day(date_raw: str, items: list[dict[str, Any]], errors: list[str]) -> dict[str, Any]:
    return {
        "date": ymd_dash(date_raw),
        "date_raw": date_raw,
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(items),
        "net_amt_total": round(sum(_amt(item) for item in items), 2),
        "items": items,
        "errors": errors,
        "note": "东财龙虎榜，行业=申万一/二/三级",
    }


class ListService:
    def __init__(self) -> None:
        self._cache = TtlCache(_MEM_TTL)

    def _latest_date(self) -> str:
        for date in recent_trade_dates(8):
            try:
                rows = fetch_details(date=date)
            except Exception:  # noqa: BLE001
                continue
            if rows:
                return date
        dates = recent_trade_dates(1)
        return dates[0] if dates else _today()

    def daily(self, date: str = "", force: bool = False) -> dict[str, Any]:
        date_raw = ymd(date) if date.strip() else self._latest_date()
        cache_key = f"daily:{date_raw}"
        if not force:
            hit = self._cache.get(cache_key)
            if hit is not None:
                return hit
            ttl = _TODAY_DISK_TTL if _is_today(date_raw) else _HIST_DISK_TTL
            disk = _load_disk("daily", date_raw, ttl)
            if disk is not None:
                self._cache.put(cache_key, disk)
                return disk

        errors: list[str] = []
        details = fetch_details(date=date_raw)
        try:
            buyers = fetch_seats("buy", date=date_raw)
        except Exception as exc:  # noqa: BLE001
            buyers = []
            errors.append(f"买入席位: {exc}")
        try:
            sellers = fetch_seats("sell", date=date_raw)
        except Exception as exc:  # noqa: BLE001
            sellers = []
            errors.append(f"卖出席位: {exc}")

        items = assemble(details, buyers, sellers)
        _attach_sw(items)
        payload = _pack_day(date_raw, items, errors)
        self._cache.put(cache_key, payload)
        _save_disk("daily", date_raw, payload)
        return payload

    def stock(self, code: str, force: bool = False) -> dict[str, Any]:
        stock = normalize_code(code)
        if not stock:
            raise ValueError("缺少有效股票代码")
        cache_key = f"stock:{stock}"
        if not force:
            hit = self._cache.get(cache_key)
            if hit is not None:
                return hit
            disk = _load_disk("stock", stock, _STOCK_DISK_TTL)
            if disk is not None:
                self._cache.put(cache_key, disk)
                return disk

        errors: list[str] = []
        details = fetch_details(code=stock)
        try:
            buyers = fetch_seats("buy", code=stock)
        except Exception as exc:  # noqa: BLE001
            buyers = []
            errors.append(f"买入席位: {exc}")
        try:
            sellers = fetch_seats("sell", code=stock)
        except Exception as exc:  # noqa: BLE001
            sellers = []
            errors.append(f"卖出席位: {exc}")

        items = assemble(details, buyers, sellers)
        _attach_sw(items)
        items.sort(key=lambda item: (item.get("date") or "", _amt(item)), reverse=True)
        name = ""
        for row in items:
            if row.get("name"):
                name = str(row["name"])
                break
        payload = {
            "code": stock,
            "name": name,
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "count": len(items),
            "items": items,
            "errors": errors,
            "note": "东财龙虎榜个股历史，行业=申万一/二/三级",
        }
        if items:
            sw = items[0]
            payload["l1_name"] = sw.get("l1_name") or ""
            payload["l2_name"] = sw.get("l2_name") or ""
            payload["l3_name"] = sw.get("l3_name") or ""
            payload["l3_code"] = sw.get("l3_code") or ""
        self._cache.put(cache_key, payload)
        _save_disk("stock", stock, payload)
        return payload


service = ListService()
