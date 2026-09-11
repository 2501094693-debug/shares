"""东财 push2 全球指数实时行情。"""

from __future__ import annotations

from typing import Any

from core.http import get_json

from world.catalog import INDICES

_PUSH2_HOSTS = (
    "https://push2delay.eastmoney.com",
    "https://push2.eastmoney.com",
    "https://82.push2.eastmoney.com",
    "https://71.push2.eastmoney.com",
)
_FIELDS = "f12,f13,f14,f2,f3,f4,f17,f15,f16,f18,f124"


def _scale(raw: Any) -> float | None:
    if raw is None or raw == "-":
        return None
    try:
        return round(float(raw) / 100.0, 4)
    except (TypeError, ValueError):
        return None


def _parse_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": str(row.get("f12") or "").strip(),
        "name": str(row.get("f14") or "").strip(),
        "price": _scale(row.get("f2")),
        "change_pct": _scale(row.get("f3")),
        "change": _scale(row.get("f4")),
        "open": _scale(row.get("f17")),
        "high": _scale(row.get("f15")),
        "low": _scale(row.get("f16")),
        "prev_close": _scale(row.get("f18")),
        "quote_time": row.get("f124"),
    }


def _fetch_batch(secids: list[str]) -> list[dict[str, Any]]:
    params = {
        "np": "2",
        "fltt": "1",
        "invt": "2",
        "fs": ",".join(secids),
        "fields": _FIELDS,
        "fid": "f3",
        "pn": "1",
        "pz": str(max(len(secids), 20)),
        "po": "1",
        "dect": "1",
        "wbp2u": "|0|0|0|web",
    }
    last_error: Exception | None = None
    for host in _PUSH2_HOSTS:
        try:
            payload = get_json(f"{host}/api/qt/clist/get", params=params, timeout=15)
            diff = (payload.get("data") or {}).get("diff") or {}
            if isinstance(diff, list):
                return [row for row in diff if isinstance(row, dict)]
            return [row for row in diff.values() if isinstance(row, dict)]
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    if last_error is not None:
        raise last_error
    return []


def fetch_indices() -> dict[str, Any]:
    """拉取目录内全部指数，按地区分组返回。"""
    secids: list[str] = []
    for block in INDICES.values():
        for item in block["items"]:
            secids.append(f"i:{item['secid']}")

    rows: list[dict[str, Any]] = []
    batch_size = 8
    for start in range(0, len(secids), batch_size):
        rows.extend(_fetch_batch(secids[start : start + batch_size]))

    by_code: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = str(row.get("f12") or "").strip()
        if code:
            by_code[code] = _parse_row(row)

    out: dict[str, Any] = {"regions": [], "items": []}
    for region, block in INDICES.items():
        region_items: list[dict[str, Any]] = []
        for item in block["items"]:
            quote = by_code.get(item["code"], {})
            row = {
                "region": region,
                "region_name": block["name"],
                "code": item["code"],
                "name": item["name"],
                **quote,
            }
            region_items.append(row)
            out["items"].append(row)
        out["regions"].append(
            {"id": region, "name": block["name"], "indices": region_items}
        )
    return out
