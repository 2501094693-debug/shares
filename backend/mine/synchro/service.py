"""本地分组 → 同花顺账号同步业务逻辑。

策略（幂等、可重入）：
1. 读本地 ``mine.store`` 分组全量成分；
2. 拉远端 ``get_account_watchlist_groups``，按名称匹配远端分组；
3. 远端不存在 → ``create_account_watchlist_group(name, securities)``；
   已存在 → ``replace_account_watchlist_group_securities`` 全量覆盖，
   保证远端与本地最终一致；
4. 远端分组 id ↔ 本地分组 id 的映射持久化到
   ``backend/cache/mine/ths_sync.json``，避免改名后重复建组。

空分组：远端不支持空成分建组，跳过并在结果中标注 ``skipped_empty``。
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any

from core.codes import normalize_code, safe_str
from core.paths import MINE_CACHE_DIR, ensure_cache_dirs

from mine import store as local_store
from mine.synchro import ths as ths_client

_MAP_FILE = MINE_CACHE_DIR / "ths_sync.json"
_lock = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _load_map() -> dict[str, Any]:
    ensure_cache_dirs()
    if not _MAP_FILE.is_file():
        return {"bindings": {}}
    try:
        raw = json.loads(_MAP_FILE.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and isinstance(raw.get("bindings"), dict):
            return {"bindings": dict(raw["bindings"])}
    except (OSError, json.JSONDecodeError):
        pass
    return {"bindings": {}}


def _save_map(bindings: dict[str, Any]) -> None:
    ensure_cache_dirs()
    tmp = _MAP_FILE.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps({"bindings": bindings, "updated_at": _now()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(_MAP_FILE)


def _frame_to_records(frame: Any) -> list[dict[str, Any]]:
    """thsdk 返回多为 pandas DataFrame（index=group_id），转成记录列表。"""
    try:
        import pandas as pd  # type: ignore

        if isinstance(frame, pd.DataFrame):
            records = frame.to_dict("records")
            index = list(frame.index)
            for rec, gid in zip(records, index):
                if isinstance(rec, dict):
                    rec.setdefault("id", gid)
            return [r for r in records if isinstance(r, dict)]
    except Exception:  # noqa: BLE001
        pass
    if isinstance(frame, dict):
        groups = frame.get("groups")
        if isinstance(groups, dict):
            return [{"id": gid, **(v if isinstance(v, dict) else {})} for gid, v in groups.items()]
        if isinstance(groups, list):
            return [g for g in groups if isinstance(g, dict)]
    if isinstance(frame, list):
        return [g for g in frame if isinstance(g, dict)]
    return []


class SynchroService:
    def status(self) -> dict[str, Any]:
        from company.line.tonghuashun import auth as _auth

        with _lock:
            bindings = _load_map()["bindings"]
        snap = _auth.status()
        return {
            "authenticated": bool(snap.get("authenticated")),
            "pending": bool(snap.get("pending")),
            "bindings": bindings,
            "bound_count": len(bindings),
        }

    def remote_groups(self) -> dict[str, Any]:
        frame = ths_client.list_remote_groups()
        return {"groups": _frame_to_records(frame), "count": len(_frame_to_records(frame))}

    def _local_group(self, group_id: str) -> dict[str, Any]:
        payload = local_store.load()
        gid = safe_str(group_id)
        for g in payload.get("groups") or []:
            if isinstance(g, dict) and safe_str(g.get("id")) == gid:
                return g
        raise KeyError(f"分组不存在: {group_id}")

    def push_group(self, group_id: str) -> dict[str, Any]:
        group = self._local_group(group_id)
        name = safe_str(group.get("name"))
        codes = [
            normalize_code(safe_str(s.get("code")))
            for s in (group.get("stocks") or [])
            if isinstance(s, dict) and normalize_code(safe_str(s.get("code")))
        ]
        if not name:
            raise ValueError("分组名称为空，无法同步")
        if not codes:
            return {"group_id": safe_str(group.get("id")), "name": name, "result": "skipped_empty",
                    "detail": "本地分组为空，远端不支持空分组，已跳过"}

        with _lock:
            bindings = _load_map()["bindings"]
            remote = _frame_to_records(ths_client.list_remote_groups())
            by_id = {safe_str(gr.get("id")): gr for gr in remote if safe_str(gr.get("id"))}
            by_name: dict[str, dict[str, Any]] = {}
            for gr in remote:
                if safe_str(gr.get("name")):
                    by_name.setdefault(safe_str(gr.get("name")), gr)

            bound_remote_id = safe_str(bindings.get(safe_str(group.get("id")), {}).get("remote_id") or bindings.get(safe_str(group.get("id"))))
            target = by_id.get(bound_remote_id) if bound_remote_id else None
            action = "replace"
            if target is None:
                target = by_name.get(name)
            if target is None:
                ths_client.create_remote_group(name, codes)
                action = "create"
            else:
                try:
                    gid_int = int(float(safe_str(target.get("id"))))
                except ValueError:
                    raise ValueError(f"远端分组 id 非法: {target.get('id')!r}")
                ths_client.replace_remote_group(gid_int, codes)

            refreshed = _frame_to_records(ths_client.list_remote_groups())
            new_target = next((g for g in refreshed if safe_str(g.get("name")) == name), None)
            if new_target is not None:
                bindings[safe_str(group.get("id"))] = {
                    "remote_id": safe_str(new_target.get("id")),
                    "remote_name": safe_str(new_target.get("name")),
                    "updated_at": _now(),
                }
                _save_map(bindings)
                remote_id = safe_str(new_target.get("id"))
            else:
                remote_id = bound_remote_id

            return {"group_id": safe_str(group.get("id")), "name": name, "codes": len(codes),
                    "action": action, "remote_id": remote_id, "result": "ok"}

    def push_all(self) -> dict[str, Any]:
        payload = local_store.load()
        groups = [g for g in (payload.get("groups") or []) if isinstance(g, dict)]
        items: list[dict[str, Any]] = []
        for g in groups:
            gid = safe_str(g.get("id"))
            try:
                items.append(self.push_group(gid))
            except PermissionError:
                raise
            except Exception as exc:  # noqa: BLE001
                items.append({"group_id": gid, "name": safe_str(g.get("name")),
                              "result": "error", "detail": str(exc)})
        ok_count = sum(1 for i in items if i.get("result") == "ok")
        return {"total": len(items), "ok": ok_count, "items": items}


synchro_service = SynchroService()
