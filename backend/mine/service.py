"""自选股票分组业务逻辑。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from core.codes import normalize_code, safe_str

from mine import store

_MAX_GROUP_NAME_LEN = 40
_MAX_GROUPS = 100
_MAX_STOCKS_PER_GROUP = 500

# 与个股行情列表对齐的行情字段
_QUOTE_KEYS = (
    "l1_name",
    "l2_name",
    "l3_name",
    "l3_code",
    "change_pct",
    "price",
    "market_cap",
    "pe_ttm",
    "pb",
    "main_net",
    "main_net_5d",
    "main_net_10d",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _lookup_name(code: str) -> str:
    """尽量从全市场索引补简称；索引未就绪则返回空串。"""
    try:
        from market.industry.service import service as industry_service

        industry_service.stocks.ensure_populated()
        hit = industry_service.stocks.get_by_code(code)
        if hit:
            return safe_str(hit.get("name"))
    except Exception:  # noqa: BLE001
        pass
    return ""


def _quote_index(*, live: bool = True) -> tuple[dict[str, dict[str, Any]], str]:
    """复用个股行情缓存，按代码索引；失败时返回空表。"""
    try:
        from market.shares.service import service as shares_service

        payload = shares_service.list(live=live)
        items = payload.get("items") or []
        by_code = {
            normalize_code(safe_str(row.get("code"))): row
            for row in items
            if isinstance(row, dict) and normalize_code(safe_str(row.get("code")))
        }
        return by_code, safe_str(payload.get("updated_at"))
    except Exception:  # noqa: BLE001
        return {}, ""


def _enrich_stocks(
    stocks: list[dict[str, Any]],
    *,
    live: bool = True,
) -> tuple[list[dict[str, Any]], str]:
    """把分组成分补上与「个股行情」列表相同的行情字段，保留加入顺序。"""
    by_code, quote_updated_at = _quote_index(live=live)
    enriched: list[dict[str, Any]] = []
    for index, raw in enumerate(stocks, start=1):
        if not isinstance(raw, dict):
            continue
        code = normalize_code(safe_str(raw.get("code")))
        if not code:
            continue
        quote = by_code.get(code) or {}
        row: dict[str, Any] = {
            "code": code,
            "name": safe_str(raw.get("name")) or safe_str(quote.get("name")) or "",
            "added_at": safe_str(raw.get("added_at")),
            "rank": index,
        }
        for key in _QUOTE_KEYS:
            if key in quote:
                row[key] = quote.get(key)
            else:
                row[key] = None if key not in ("l1_name", "l2_name", "l3_name", "l3_code") else ""
        enriched.append(row)
    return enriched, quote_updated_at


def _public_group(
    group: dict[str, Any],
    *,
    with_stocks: bool = True,
    live: bool = True,
) -> dict[str, Any]:
    stocks = [dict(s) for s in (group.get("stocks") or []) if isinstance(s, dict)]
    out: dict[str, Any] = {
        "id": safe_str(group.get("id")),
        "name": safe_str(group.get("name")),
        "created_at": safe_str(group.get("created_at")),
        "updated_at": safe_str(group.get("updated_at")),
        "count": len(stocks),
    }
    if with_stocks:
        enriched, quote_updated_at = _enrich_stocks(stocks, live=live)
        out["stocks"] = enriched
        if quote_updated_at:
            out["quote_updated_at"] = quote_updated_at
    return out


def _find_group(groups: list[dict[str, Any]], group_id: str) -> dict[str, Any] | None:
    gid = safe_str(group_id)
    for group in groups:
        if safe_str(group.get("id")) == gid:
            return group
    return None


class MineService:
    def list_groups(self) -> dict[str, Any]:
        with store._lock:
            payload = store.load()
            groups = [_public_group(g, with_stocks=False) for g in payload["groups"]]
        return {"groups": groups, "count": len(groups)}

    def get_group(self, group_id: str) -> dict[str, Any]:
        with store._lock:
            payload = store.load()
            group = _find_group(payload["groups"], group_id)
            if group is None:
                raise KeyError(f"分组不存在: {group_id}")
            return _public_group(group, with_stocks=True)

    def create_group(self, name: str) -> dict[str, Any]:
        name = safe_str(name)
        if not name:
            raise ValueError("分组名称不能为空")
        if len(name) > _MAX_GROUP_NAME_LEN:
            raise ValueError(f"分组名称最多 {_MAX_GROUP_NAME_LEN} 字")

        with store._lock:
            payload = store.load()
            groups = payload["groups"]
            if len(groups) >= _MAX_GROUPS:
                raise ValueError(f"最多创建 {_MAX_GROUPS} 个分组")
            for g in groups:
                if safe_str(g.get("name")) == name:
                    raise ValueError(f"分组名称已存在: {name}")

            stamp = _now_iso()
            group = {
                "id": _new_id(),
                "name": name,
                "created_at": stamp,
                "updated_at": stamp,
                "stocks": [],
            }
            groups.append(group)
            store.save(payload)
            return _public_group(group, with_stocks=True)

    def delete_group(self, group_id: str) -> dict[str, Any]:
        with store._lock:
            payload = store.load()
            groups = payload["groups"]
            group = _find_group(groups, group_id)
            if group is None:
                raise KeyError(f"分组不存在: {group_id}")
            snapshot = _public_group(group, with_stocks=True)
            payload["groups"] = [
                g for g in groups if safe_str(g.get("id")) != safe_str(group_id)
            ]
            store.save(payload)
            return snapshot

    def add_stocks(
        self,
        group_id: str,
        codes: list[str],
        *,
        names: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        raw_codes = [safe_str(c) for c in (codes or []) if safe_str(c)]
        if not raw_codes:
            raise ValueError("缺少股票代码")

        name_map = {
            normalize_code(k): safe_str(v)
            for k, v in (names or {}).items()
            if normalize_code(k)
        }

        with store._lock:
            payload = store.load()
            group = _find_group(payload["groups"], group_id)
            if group is None:
                raise KeyError(f"分组不存在: {group_id}")

            stocks = [s for s in (group.get("stocks") or []) if isinstance(s, dict)]
            existing = {
                normalize_code(safe_str(s.get("code")))
                for s in stocks
                if normalize_code(safe_str(s.get("code")))
            }

            added: list[dict[str, Any]] = []
            skipped: list[str] = []
            stamp = _now_iso()

            for raw in raw_codes:
                code = normalize_code(raw)
                if not code:
                    continue
                if code in existing:
                    skipped.append(code)
                    continue
                if len(stocks) + len(added) >= _MAX_STOCKS_PER_GROUP:
                    raise ValueError(f"每个分组最多 {_MAX_STOCKS_PER_GROUP} 只股票")

                name = name_map.get(code) or _lookup_name(code)
                row = {"code": code, "name": name, "added_at": stamp}
                added.append(row)
                existing.add(code)

            if not added and skipped:
                # 全部已存在也算成功，返回当前分组
                return {
                    "group": _public_group(group, with_stocks=True),
                    "added": [],
                    "skipped": skipped,
                }
            if not added:
                raise ValueError("没有有效的股票代码")

            stocks.extend(added)
            group["stocks"] = stocks
            group["updated_at"] = stamp
            store.save(payload)
            return {
                "group": _public_group(group, with_stocks=True),
                "added": added,
                "skipped": skipped,
            }

    def remove_stocks(self, group_id: str, codes: list[str]) -> dict[str, Any]:
        raw_codes = [normalize_code(c) for c in (codes or [])]
        want = {c for c in raw_codes if c}
        if not want:
            raise ValueError("缺少股票代码")

        with store._lock:
            payload = store.load()
            group = _find_group(payload["groups"], group_id)
            if group is None:
                raise KeyError(f"分组不存在: {group_id}")

            stocks = [s for s in (group.get("stocks") or []) if isinstance(s, dict)]
            kept: list[dict[str, Any]] = []
            removed: list[dict[str, Any]] = []
            for row in stocks:
                code = normalize_code(safe_str(row.get("code")))
                if code and code in want:
                    removed.append(dict(row))
                else:
                    kept.append(row)

            if not removed:
                raise KeyError("分组内未找到指定股票")

            group["stocks"] = kept
            group["updated_at"] = _now_iso()
            store.save(payload)
            return {
                "group": _public_group(group, with_stocks=True),
                "removed": removed,
            }


service = MineService()
