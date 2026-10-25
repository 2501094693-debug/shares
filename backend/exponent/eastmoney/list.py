"""枚举 / 搜索东财指数（``clist/get``）。"""

from __future__ import annotations

from typing import Any

from core.fmt import to_float
from core.http import get_json

from exponent.eastmoney.catalog import CATEGORIES, all_items as catalog_items

_HOSTS = (
    "https://push2.eastmoney.com/api/qt/clist/get",
    "https://push2delay.eastmoney.com/api/qt/clist/get",
    "https://82.push2.eastmoney.com/api/qt/clist/get",
)
_HEADERS = {
    "Referer": "https://quote.eastmoney.com/",
    "Accept": "application/json, text/plain, */*",
}
_FIELDS = "f12,f13,f14,f2,f3,f4,f15,f16,f17,f18,f5,f6"
_UT = "fa5fd1943c7b386f172d6893dbfba10b"
_PAGE = 100


def _page(fs: str, pn: int) -> dict[str, Any]:
    params = {
        "pn": str(pn),
        "pz": str(_PAGE),
        "po": "1",
        "np": "1",
        "fltt": "2",
        "invt": "2",
        "fid": "f3",
        "fs": fs,
        "fields": _FIELDS,
        "ut": _UT,
    }
    last_exc: Exception | None = None
    for url in _HOSTS:
        try:
            payload = get_json(url, params=params, headers=_HEADERS, timeout=12)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            continue
        data = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(data, dict):
            return payload
        last_exc = RuntimeError("东财指数列表返回非 JSON")
    raise RuntimeError(f"东财指数列表失败: {last_exc}")


def _rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data") or {}
    diff = data.get("diff") or []
    if isinstance(diff, dict):
        diff = list(diff.values())
    return [item for item in diff if isinstance(item, dict)]


def _normalize_item(row: dict[str, Any]) -> dict[str, Any] | None:
    code = str(row.get("f12") or "").strip()
    if not code:
        return None
    if code.isdigit() and len(code) <= 6:
        code = code.zfill(6)
    market_id = row.get("f13")
    try:
        mid = int(market_id)
    except (TypeError, ValueError):
        mid = 1
    secid = f"{mid}.{code}"
    return {
        "code": code,
        "name": str(row.get("f14") or "").strip(),
        "secid": secid,
        "market": mid,
        "price": to_float(row.get("f2")),
        "change_pct": to_float(row.get("f3")),
        "change": to_float(row.get("f4")),
        "high": to_float(row.get("f15")),
        "low": to_float(row.get("f16")),
        "open": to_float(row.get("f17")),
        "prev_close": to_float(row.get("f18")),
        "volume": to_float(row.get("f5")),
        "amount": to_float(row.get("f6")),
    }


def list_indices(
    categories: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """按东财分类拉取指数列表。

    ``categories`` 为空则拉 catalog 里全部分类（important / sse / szse / csi）。
    """
    wanted = [
        c.strip().lower()
        for c in (categories or list(CATEGORIES.keys()))
        if str(c).strip()
    ]
    if not wanted:
        wanted = list(CATEGORIES.keys())

    groups: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    for cat_id in wanted:
        meta = CATEGORIES.get(cat_id)
        if not meta:
            continue
        fs = meta["fs"]
        items: list[dict[str, Any]] = []
        pn = 1
        total = None
        while True:
            payload = _page(fs, pn)
            data = payload.get("data") or {}
            if total is None:
                try:
                    total = int(data.get("total") or 0)
                except (TypeError, ValueError):
                    total = 0
            rows = _rows(payload)
            if not rows:
                break
            for row in rows:
                item = _normalize_item(row)
                if not item:
                    continue
                item["category"] = cat_id
                item["category_name"] = meta["name"]
                items.append(item)
                if item["secid"] not in seen:
                    seen.add(item["secid"])
                    all_rows.append(item)
            if pn * _PAGE >= max(total, 0) or len(rows) < _PAGE:
                break
            pn += 1
            if pn > 50:
                break

        groups.append(
            {
                "category": cat_id,
                "category_name": meta["name"],
                "fs": fs,
                "count": len(items),
                "items": items,
            }
        )

    return {
        "source": "eastmoney",
        "categories": wanted,
        "count": len(all_rows),
        "groups": groups,
        "items": all_rows,
    }


def search_indices(keyword: str, *, limit: int = 20) -> dict[str, Any]:
    """按名称 / 代码在目录 + 重要指数列表中搜索。"""
    kw = (keyword or "").strip()
    if not kw:
        return {"source": "eastmoney", "keyword": "", "count": 0, "items": []}

    kw_l = kw.lower()
    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    for item in catalog_items():
        code = str(item.get("code") or "")
        name = str(item.get("name") or "")
        secid = str(item.get("secid") or "")
        if (
            kw_l in code.lower()
            or kw_l in name.lower()
            or kw_l in secid.lower()
            or kw == code
        ):
            row = {
                "code": code,
                "name": name,
                "secid": secid,
                "group": item.get("group"),
                "group_name": item.get("group_name"),
            }
            items.append(row)
            seen.add(secid)

    # 再扫一遍重要指数列表补漏
    try:
        listed = list_indices(["important"])
        for item in listed.get("items") or []:
            secid = str(item.get("secid") or "")
            if secid in seen:
                continue
            code = str(item.get("code") or "")
            name = str(item.get("name") or "")
            if kw_l in code.lower() or kw_l in name.lower() or kw == code:
                items.append(
                    {
                        "code": code,
                        "name": name,
                        "secid": secid,
                        "price": item.get("price"),
                        "change_pct": item.get("change_pct"),
                    }
                )
                seen.add(secid)
            if len(items) >= max(1, min(int(limit or 20), 100)):
                break
    except Exception:  # noqa: BLE001
        pass

    return {
        "source": "eastmoney",
        "keyword": kw,
        "count": len(items[: max(1, min(int(limit or 20), 100))]),
        "items": items[: max(1, min(int(limit or 20), 100))],
    }
