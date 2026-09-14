"""同花顺个股资金流：stockpage spService 请求与字段解析。"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from core.codes import normalize_code
from core.fmt import to_float
from core.http import get_text

logger = logging.getLogger(__name__)

_STOCKPAGE = "https://stockpage.10jqka.com.cn"
_WAN_YUAN = 10000.0
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}


def _referer(code: str) -> dict[str, str]:
    norm = normalize_code(code) or code
    return {**_HEADERS, "Referer": f"{_STOCKPAGE}/{norm}/"}


def wan_to_yuan(value: Any) -> float | None:
    """同花顺 spService 金额字段为万元，与东财口径对齐为元。"""
    number = to_float(value)
    if number is None:
        return None
    return round(number * _WAN_YUAN, 2)


def fetch_sp_json(code: str, path: str) -> dict[str, Any]:
    """``spService/{code}/{path}`` → JSON dict。"""
    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")
    url = f"{_STOCKPAGE}/spService/{norm}/{path.lstrip('/')}"
    text = get_text(url, timeout=15, headers=_referer(norm))
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.info("ths fundflow json skip %s: %s", path, exc)
        return {}
    return payload if isinstance(payload, dict) else {}


def _flow_name_kind(name: str) -> tuple[str, str] | None:
    """``大单流入`` → (``big``, ``in``)。"""
    text = str(name or "").strip()
    if not text:
        return None
    tier = ""
    if "超大" in text:
        tier = "super"
    elif "大单" in text:
        tier = "big"
    elif "中单" in text:
        tier = "mid"
    elif "小单" in text:
        tier = "small"
    elif "主力" in text:
        tier = "main"
    else:
        return None
    if "流入" in text:
        return tier, "in"
    if "流出" in text:
        return tier, "out"
    return None


def parse_flash_rows(rows: list[Any]) -> dict[str, float | None]:
    """realFunds.flash → 各档流入/流出（元，流出为负）。"""
    nets: dict[str, float] = {
        "main_net": 0.0,
        "super_net": 0.0,
        "big_net": 0.0,
        "mid_net": 0.0,
        "small_net": 0.0,
    }
    has_value = False
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        parsed = _flow_name_kind(str(row.get("name") or ""))
        amount = wan_to_yuan(row.get("sr"))
        if not parsed or amount is None:
            continue
        tier, direction = parsed
        signed = amount if direction == "in" else -amount
        key = f"{tier}_net"
        if key in nets:
            nets[key] = nets.get(key, 0.0) + signed
            has_value = True
    if not has_value:
        return {key: None for key in nets}
    return {key: round(value, 2) for key, value in nets.items()}


def parse_diff(diff: dict[str, Any] | None) -> dict[str, float | None]:
    """lineFunds.diff → 大/中/小单净额与占比。"""
    node = diff if isinstance(diff, dict) else {}
    return {
        "main_net": wan_to_yuan(node.get("ddje")),
        "main_net_pct": to_float(node.get("ddjb")),
        "big_net": wan_to_yuan(node.get("ddje")),
        "big_net_pct": to_float(node.get("ddjb")),
        "mid_net": wan_to_yuan(node.get("zdje")),
        "mid_net_pct": to_float(node.get("zdjb")),
        "small_net": wan_to_yuan(node.get("xdje")),
        "small_net_pct": to_float(node.get("xdjb")),
    }


def parse_title(title: dict[str, Any] | None) -> dict[str, float | None]:
    """realFunds.title → 主力流入/流出/净额（元）。"""
    node = title if isinstance(title, dict) else {}
    inflow = wan_to_yuan(node.get("zlr"))
    outflow = wan_to_yuan(node.get("zlc"))
    net = wan_to_yuan(node.get("je"))
    if net is None and inflow is not None and outflow is not None:
        net = round(inflow - outflow, 2)
    return {
        "main_inflow": inflow,
        "main_outflow": outflow,
        "main_net": net,
    }


def _today_prefix() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def parse_line_points(raw: str) -> list[dict[str, Any]]:
    """lineFunds.line → 分钟序列。字段为万元，对齐东财输出为元。"""
    items: list[dict[str, Any]] = []
    for chunk in str(raw or "").split("|"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = chunk.split(";")
        if len(parts) < 4:
            continue
        time_s = parts[0].strip()
        if not time_s:
            continue
        day = _today_prefix()
        stamp = f"{day} {time_s}" if " " not in time_s else time_s
        items.append(
            {
                "time": stamp,
                "main_net": wan_to_yuan(parts[1]),
                "mid_net": wan_to_yuan(parts[2]),
                "small_net": wan_to_yuan(parts[3]) if abs(to_float(parts[3]) or 0) > 20 else None,
                "extra": to_float(parts[3]),
            }
        )
    return items
