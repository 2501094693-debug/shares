"""同花顺当日资金流拆分（``thsdk.list_security_daily_capital_flows``）。

把当日成交额按「主动/被动 × 买/卖 × 超大/大/中/小」拆开；
每只股票当天只有 1 行快照，无历史日期参数。需实盘扫码登录。

    python -m company.statistics.fundflow.tonghuashun.daily_capital 600519
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[4]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from core.codes import normalize_code
from core.fmt import to_float

# (对外档位名, 源站后缀)
_TIERS: tuple[tuple[str, str], ...] = (
    ("super", "x_large"),
    ("big", "large"),
    ("mid", "medium"),
    ("small", "small"),
)
_SIDES: tuple[str, ...] = (
    "active_buy",
    "active_sell",
    "passive_buy",
    "passive_sell",
)


def _hq_security(code: str) -> str:
    from company.statistics.fundflow.tonghuashun import hq as _hq

    return _hq.hq_security(code)


def _money(value: Any) -> float | None:
    number = to_float(value)
    if number is None:
        return None
    return round(float(number), 2)


def _sub(left: float | None, right: float | None) -> float | None:
    if left is None and right is None:
        return None
    return round(float(left or 0) - float(right or 0), 2)


def _add(*values: float | None) -> float | None:
    present = [float(v) for v in values if v is not None]
    if not present:
        return None
    return round(sum(present), 2)


def _parse_row(row: dict[str, Any], *, code: str) -> dict[str, Any]:
    turnover = _money(row.get("turnover"))
    tiers: dict[str, Any] = {}
    flat: dict[str, float | None] = {}

    for alias, suffix in _TIERS:
        active_buy = _money(row.get(f"active_buy_{suffix}"))
        active_sell = _money(row.get(f"active_sell_{suffix}"))
        passive_buy = _money(row.get(f"passive_buy_{suffix}"))
        passive_sell = _money(row.get(f"passive_sell_{suffix}"))
        tier = {
            "active_buy": active_buy,
            "active_sell": active_sell,
            "passive_buy": passive_buy,
            "passive_sell": passive_sell,
            "active_net": _sub(active_buy, active_sell),
            "passive_net": _sub(passive_buy, passive_sell),
            "buy": _add(active_buy, passive_buy),
            "sell": _add(active_sell, passive_sell),
        }
        # 净流入：该档全部买入 − 全部卖出
        tier["net"] = _sub(tier["buy"], tier["sell"])
        tiers[alias] = tier
        for side in _SIDES:
            flat[f"{side}_{alias}"] = tier[side]

    active_buy = _add(*(tiers[a]["active_buy"] for a, _ in _TIERS))
    active_sell = _add(*(tiers[a]["active_sell"] for a, _ in _TIERS))
    passive_buy = _add(*(tiers[a]["passive_buy"] for a, _ in _TIERS))
    passive_sell = _add(*(tiers[a]["passive_sell"] for a, _ in _TIERS))

    return {
        "code": code,
        "turnover": turnover,
        "active_buy": active_buy,
        "active_sell": active_sell,
        "passive_buy": passive_buy,
        "passive_sell": passive_sell,
        "active_net": _sub(active_buy, active_sell),
        "passive_net": _sub(passive_buy, passive_sell),
        "buy": _add(active_buy, passive_buy),
        "sell": _add(active_sell, passive_sell),
        "net": _sub(_add(active_buy, passive_buy), _add(active_sell, passive_sell)),
        # 与东财 snapshot 字段对齐的档位净流入（买−卖）
        "super_net": tiers["super"]["net"],
        "big_net": tiers["big"]["net"],
        "mid_net": tiers["mid"]["net"],
        "small_net": tiers["small"]["net"],
        "tiers": tiers,
        "raw": {key: _money(row.get(key)) for key in row if key != "security"},
    }


def fetch_daily_capital(
    code: str,
    *,
    timeout: float | None = None,
) -> dict[str, Any]:
    """拉取一只股票的当日资金流拆分快照。"""
    import thsdk
    from company.line.tonghuashun import auth as _ths_auth

    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")
    if not _ths_auth.ensure(timeout=3):
        raise RuntimeError("THS_NEED_QRCODE:同花顺需扫码登录，前端打开扫码弹窗后重试")

    security = _hq_security(norm)
    if not security:
        raise ValueError("无法映射同花顺证券代码")

    kwargs: dict[str, Any] = {"securities": [security]}
    if timeout is not None:
        kwargs["timeout"] = timeout
    frame = thsdk.list_security_daily_capital_flows(**kwargs)
    records = frame.to_dict("records") if hasattr(frame, "to_dict") else list(frame or [])
    row = next((item for item in records if isinstance(item, dict)), None)
    if not row:
        raise RuntimeError(f"{norm} 当日资金流为空（非交易日或无权限）")

    parsed = _parse_row(row, code=norm)
    return {
        "code": norm,
        "name": "",
        "period": "daily_capital",
        "source": "tonghuashun",
        "method": "thsdk:daily_capital_flows",
        "count": 1,
        "notes": [
            "当日快照：主动/被动 × 买/卖 × 超大/大/中/小；金额单位元",
            "小单通常只有 active_*，无 passive_*",
            "接口无历史日期参数，不能拉多日序列",
        ],
        **parsed,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="同花顺当日资金流拆分（需实盘登录）")
    parser.add_argument("code", help="股票代码，如 600519")
    args = parser.parse_args()
    pack = fetch_daily_capital(args.code)
    print(json.dumps(pack, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
