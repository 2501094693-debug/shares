"""枚举同花顺指数市场全部标的（USHI / USZI / UZZI / USTI）。"""

from __future__ import annotations

from typing import Any

from exponent.tonghuashun.catalog import MARKETS, all_items as catalog_items

_DEFAULT_MARKETS = tuple(MARKETS.keys())
_PAGE = 200


def _security_to_display() -> dict[str, str]:
    """目录内 security → 公开 6 位码（上证 1A/1B 内部码无法机械换算）。"""
    return {
        str(item["security"]): str(item["code"])
        for item in catalog_items()
        if item.get("security") and item.get("code")
    }


def _display_code(security: str, raw_code: str, known: dict[str, str]) -> str:
    if security in known:
        return known[security]
    code = (raw_code or "").strip()
    if code.isdigit():
        return code.zfill(6) if len(code) <= 6 else code
    # 上证内部码无目录命中时保留原样，避免 1B0007→000007 这种错映射
    return code or security[4:]


def list_indices(
    markets: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """分页拉取指定市场全部指数。"""
    import thsdk
    from company.line.tonghuashun import auth as _ths_auth

    if not _ths_auth.ensure(timeout=3):
        raise RuntimeError("THS_NEED_QRCODE:同花顺需扫码登录，前端打开扫码弹窗后重试")

    wanted = [m.strip().upper() for m in (markets or _DEFAULT_MARKETS) if m.strip()]
    if not wanted:
        wanted = list(_DEFAULT_MARKETS)

    known = _security_to_display()
    groups: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []

    for market in wanted:
        items: list[dict[str, Any]] = []
        start = 0
        while True:
            frame = thsdk.market_securities(market, start=start, count=_PAGE)
            if frame is None or len(frame) == 0:
                break
            rows = frame.to_dict("records")
            for row in rows:
                security = str(row.get("full_code") or "").strip()
                raw_code = str(row.get("code") or "").strip()
                name = str(row.get("name") or "").strip()
                if not security:
                    continue
                item = {
                    "code": _display_code(security, raw_code, known),
                    "raw_code": raw_code,
                    "name": name,
                    "security": security,
                    "market": market,
                }
                items.append(item)
                all_rows.append(item)
            n = len(rows)
            start += n
            if n < _PAGE:
                break

        groups.append(
            {
                "market": market,
                "market_name": MARKETS.get(market, market),
                "count": len(items),
                "items": items,
            }
        )

    return {
        "source": "tonghuashun",
        "markets": wanted,
        "count": len(all_rows),
        "groups": groups,
        "items": all_rows,
    }


def search_indices(keyword: str, *, limit: int = 20) -> dict[str, Any]:
    """按名称 / 代码搜索指数。"""
    import thsdk
    from company.line.tonghuashun import auth as _ths_auth

    kw = (keyword or "").strip()
    if not kw:
        return {"source": "tonghuashun", "keyword": "", "count": 0, "items": []}
    if not _ths_auth.ensure(timeout=3):
        raise RuntimeError("THS_NEED_QRCODE:同花顺需扫码登录，前端打开扫码弹窗后重试")

    frame = thsdk.search_symbols(kw)
    prefer = set(MARKETS.keys())
    items: list[dict[str, Any]] = []
    if frame is not None and len(frame) > 0:
        for row in frame.to_dict("records"):
            market = str(row.get("market") or "")
            if prefer and market not in prefer:
                continue
            security = str(row.get("full_code") or "").strip()
            if not security:
                continue
            display = str(row.get("code_display") or row.get("code") or "").strip()
            if display.isdigit() and len(display) <= 6:
                display = display.zfill(6)
            items.append(
                {
                    "code": display,
                    "name": str(row.get("name") or "").strip(),
                    "security": security,
                    "market": market,
                    "market_display": str(row.get("market_display") or ""),
                }
            )
            if len(items) >= max(1, min(int(limit or 20), 100)):
                break

    return {
        "source": "tonghuashun",
        "keyword": kw,
        "count": len(items),
        "items": items,
    }
