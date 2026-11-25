"""同花顺当日资金流拆分（``thsdk.list_security_daily_capital_flows``）。

把当日成交额按「主动/被动 × 买/卖 × 超大/大/中/小」拆开；
每只股票当天只有 1 行快照，无历史日期参数。需实盘扫码登录。

    python -m company.statistics.fundflow.tonghuashun.daily_capital 600519
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[4]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from core.codes import normalize_code
from core.fmt import to_float

logger = logging.getLogger(__name__)

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

    # 同花顺不提供小单被动方向（passive_buy_small / passive_sell_small）。
    # 按成交恒等式推断：每笔成交必有一方主动、一方被动且金额相同，因此
    #   被动买合计 = 主动卖合计，被动卖合计 = 主动买合计
    #   小单被动买 = 主动卖合计 − (超大+大+中 被动买)
    #   小单被动卖 = 主动买合计 − (超大+大+中 被动卖)
    inferred: list[str] = []
    small = tiers["small"]
    others = [alias for alias, _ in _TIERS if alias != "small"]
    known_passive_buy = _add(*(tiers[a]["passive_buy"] for a in others))
    known_passive_sell = _add(*(tiers[a]["passive_sell"] for a in others))
    active_sell_total = _add(*(tiers[a]["active_sell"] for a, _ in _TIERS))
    active_buy_total = _add(*(tiers[a]["active_buy"] for a, _ in _TIERS))
    if (
        small["passive_buy"] is None
        and known_passive_buy is not None
        and active_sell_total is not None
    ):
        small["passive_buy"] = round(active_sell_total - known_passive_buy, 2)
        inferred.append("passive_buy")
    if (
        small["passive_sell"] is None
        and known_passive_sell is not None
        and active_buy_total is not None
    ):
        small["passive_sell"] = round(active_buy_total - known_passive_sell, 2)
        inferred.append("passive_sell")
    if inferred:
        small["passive_net"] = _sub(small["passive_buy"], small["passive_sell"])
        small["buy"] = _add(small["active_buy"], small["passive_buy"])
        small["sell"] = _add(small["active_sell"], small["passive_sell"])
        small["net"] = _sub(small["buy"], small["sell"])
        small["passive_inferred"] = True

    for alias, _ in _TIERS:
        for side in _SIDES:
            flat[f"{side}_{alias}"] = tiers[alias][side]

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


def _empty_tier(net: float | None = None) -> dict[str, Any]:
    return {
        "active_buy": None,
        "active_sell": None,
        "passive_buy": None,
        "passive_sell": None,
        "active_net": None,
        "passive_net": None,
        "buy": None,
        "sell": None,
        "net": None if net is None else round(float(net), 2),
    }


def _from_eastmoney_snapshot(code: str) -> dict[str, Any]:
    """同花顺通道不可用时：东财档位净流入快照（无主动/被动拆分）。"""
    from company.statistics.fundflow.eastmoney.stock import fetch_snapshot

    snap = fetch_snapshot(code)
    tiers = {
        "super": _empty_tier(snap.get("super_net")),
        "big": _empty_tier(snap.get("big_net")),
        "mid": _empty_tier(snap.get("mid_net")),
        "small": _empty_tier(snap.get("small_net")),
    }
    # 合计 = 超大+大+中+小四档净流入之和（理论上≈0）；主力净流入单独保留
    tier_nets = [tiers[k]["net"] for k, _ in _TIERS if tiers[k]["net"] is not None]
    tier_sum = round(sum(float(v) for v in tier_nets), 2) if tier_nets else None
    main_net = snap.get("main_net")
    if main_net is not None:
        main_net = round(float(main_net), 2)
    return {
        "code": code,
        "name": str(snap.get("name") or ""),
        "period": "daily_capital",
        "source": "eastmoney",
        "method": "eastmoney:snapshot",
        "view": "net_only",
        "count": 1,
        "turnover": None,
        "active_buy": None,
        "active_sell": None,
        "passive_buy": None,
        "passive_sell": None,
        "active_net": None,
        "passive_net": None,
        "buy": None,
        "sell": None,
        "net": tier_sum,
        "main_net": main_net,
        "super_net": tiers["super"]["net"],
        "big_net": tiers["big"]["net"],
        "mid_net": tiers["mid"]["net"],
        "small_net": tiers["small"]["net"],
        "tiers": tiers,
        "raw": {
            "main_net": snap.get("main_net"),
            "super_net": snap.get("super_net"),
            "big_net": snap.get("big_net"),
            "mid_net": snap.get("mid_net"),
            "small_net": snap.get("small_net"),
        },
        "notes": [
            "同花顺资金流通道不可用，已降级东财档位净流入（无主动/被动拆分）",
            "net 为四档净流入之和；main_net 为东财主力净流入（超大+大）",
            "金额单位元；口径与同花顺主动/被动矩阵不同，仅作对照",
        ],
    }


def _fetch_ths_daily_capital(
    code: str,
    *,
    timeout: float | None = None,
) -> dict[str, Any]:
    import thsdk
    from company.line.tonghuashun import auth as _ths_auth

    if not _ths_auth.ensure(timeout=3):
        raise RuntimeError("THS_NEED_QRCODE:同花顺需扫码登录，前端打开扫码弹窗后重试")

    security = _hq_security(code)
    if not security:
        raise ValueError("无法映射同花顺证券代码")

    kwargs: dict[str, Any] = {"securities": [security]}
    if timeout is not None:
        kwargs["timeout"] = timeout
    frame = thsdk.list_security_daily_capital_flows(**kwargs)
    records = frame.to_dict("records") if hasattr(frame, "to_dict") else list(frame or [])
    row = next((item for item in records if isinstance(item, dict)), None)
    if not row:
        raise RuntimeError(f"{code} 当日资金流为空（非交易日或无权限）")

    parsed = _parse_row(row, code=code)
    return {
        "code": code,
        "name": "",
        "period": "daily_capital",
        "source": "tonghuashun",
        "method": "thsdk:daily_capital_flows",
        "view": "full",
        "count": 1,
        "notes": [
            "当日快照：主动/被动 × 买/卖 × 超大/大/中/小；金额单位元",
            "小单 passive_* 为推断值：按 被动买合计=主动卖合计、被动卖合计=主动买合计 反推（tiers.small.passive_inferred=true）",
            "接口无历史日期参数，不能拉多日序列",
        ],
        **parsed,
    }


def fetch_daily_capital(
    code: str,
    *,
    timeout: float | None = None,
) -> dict[str, Any]:
    """拉取一只股票的当日资金流拆分快照。

    同花顺 thsdk 优先；通道失败时降级东财档位净流入。
    """
    norm = normalize_code(code)
    if not norm:
        raise ValueError("无效股票代码")

    try:
        return _fetch_ths_daily_capital(norm, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        # 未登录 / 通道异常都降级东财净流入（不依赖同花顺会话）
        logger.info("daily_capital thsdk skip %s: %s", norm, exc)

    return _from_eastmoney_snapshot(norm)


def main() -> None:
    parser = argparse.ArgumentParser(description="同花顺当日资金流拆分（需实盘登录）")
    parser.add_argument("code", help="股票代码，如 600519")
    args = parser.parse_args()
    pack = fetch_daily_capital(args.code)
    print(json.dumps(pack, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
