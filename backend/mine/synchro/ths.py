"""同花顺账号自选分组 thin client。

证券入参格式（thsdk ``SecurityInput``）：
- 字符串：``USHA600519`` / ``USZA000001`` / ``UBJA430047``，即
  ``市场前缀(4位) + 代码``；
- 本地只有 6 位数字代码，按 ``core.codes.detect_market`` 推断市场：
  沪 ``60/68`` → ``USHA``，深 ``00/30`` → ``USZA``，北 ``8/4`` → ``UBJA``。

全部写操作都会修改账号远端数据，调用前必须 ``auth.ensure()`` 通过。
"""

from __future__ import annotations

from typing import Any

from core.codes import detect_market, normalize_code

_PREFIX = {"sse": "USHA", "szse": "USZA", "bse": "UBJA"}


def to_ths_security(code: str) -> str:
    c = normalize_code(code)
    if not c:
        raise ValueError(f"无效股票代码: {code!r}")
    prefix = _PREFIX.get(detect_market(c), "USHA")
    return f"{prefix}{c}"


def to_ths_securities(codes: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in codes or []:
        c = normalize_code(raw)
        if not c or c in seen:
            continue
        seen.add(c)
        out.append(to_ths_security(c))
    return out


def _ensure_auth() -> None:
    from company.line.tonghuashun import auth as _auth

    if _auth.is_authenticated() or _auth.ensure():
        return
    raise PermissionError("THS_NEED_QRCODE: 同花顺未登录，请先扫码登录后再同步")


def _call(fn_name: str, **kwargs: Any) -> Any:
    _ensure_auth()
    import thsdk

    fn = getattr(thsdk, fn_name)
    try:
        return fn(**kwargs)
    except Exception as exc:
        name = type(exc).__name__
        if "uth" in name or "ogin" in name or "ession" in name:
            from company.line.tonghuashun import auth as _auth

            _auth.mark_need_auth()
            raise PermissionError(f"THS_NEED_QRCODE: 同花顺会话失效，请重新扫码（{exc}）") from exc
        raise


def list_remote_groups() -> Any:
    return _call("get_account_watchlist_groups")


def create_remote_group(name: str, codes: list[str]) -> Any:
    return _call("create_account_watchlist_group", name=name, securities=to_ths_securities(codes))


def replace_remote_group(group_id: int, codes: list[str]) -> Any:
    return _call(
        "replace_account_watchlist_group_securities",
        group_id=group_id,
        securities=to_ths_securities(codes),
    )


def delete_remote_group(group_id: int) -> Any:
    return _call("delete_account_watchlist_group", group_id=group_id)
