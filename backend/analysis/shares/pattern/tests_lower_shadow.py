"""近几日收下影方案：合成 K 线断言（无网络）。

在 backend 目录::

    python -m analysis.shares.pattern.tests_lower_shadow
"""

from __future__ import annotations

from analysis.shares.pattern.scheme import evaluate_scheme, normalize_scheme

DATES = ["2026-09-22", "2026-09-23", "2026-09-24", "2026-09-25", "2026-09-26"]
TRADE_NEWEST_FIRST = list(reversed(DATES))


def _hammer(date: str) -> dict:
    # 下影占振幅约 87%，且下影 > 实体
    return {
        "date": date,
        "open": 10.0,
        "high": 10.15,
        "low": 9.0,
        "close": 10.1,
        "volume": 1000,
    }


def _solid(date: str) -> dict:
    # 几乎无下影、实体主导
    return {
        "date": date,
        "open": 10.0,
        "high": 10.6,
        "low": 9.95,
        "close": 10.5,
        "volume": 1000,
    }


def _bars(kinds: list[str]) -> list[dict]:
    """kinds 与 DATES 对齐，旧→新；'h' 收下影，其它为实体阳线。"""
    out = []
    for date, kind in zip(DATES, kinds):
        out.append(_hammer(date) if kind == "h" else _solid(date))
    return out


def _recent_scheme() -> dict:
    return normalize_scheme(
        {
            "id": "recent_lower_shadow",
            "logic": "and",
            "groups": [
                {
                    "id": "lower_shadow",
                    "min_hits": 2,
                    "days": [
                        {"offset": i, "lower_ratio_min": 0.35, "lower_ge_body": True}
                        for i in range(5)
                    ],
                }
            ],
        },
        trade_dates=TRADE_NEWEST_FIRST,
    )


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def main() -> int:
    scheme = _recent_scheme()

    miss = evaluate_scheme(_bars(["s", "s", "s", "h", "s"]), scheme)
    _assert(miss is None, "仅 1/5 日收下影不应入选")

    hit = evaluate_scheme(_bars(["s", "s", "s", "h", "h"]), scheme)
    _assert(hit is not None, "近两日连续收下影应入选")
    _assert(hit["shadow_count"] == 2, f"shadow_count 应为 2，实际 {hit['shadow_count']}")
    _assert(hit["hit_lower_shadow"], "应标记 hit_lower_shadow")
    _assert(hit.get("quiet_count") == 0, f"无缩实体分支时 quiet_count 应为 0，实际 {hit.get('quiet_count')}")
    _assert(
        all(d.get("is_lower_shadow") for d in hit.get("days") or []),
        "命中日应标 is_lower_shadow",
    )
    _assert(
        sum(1 for d in (hit.get("window_days") or []) if d.get("is_lower_shadow")) == 2,
        "window_days 中应有 2 日标收下影",
    )

    recent = evaluate_scheme(_bars(["s", "s", "s", "h", "h"]), scheme)
    older = evaluate_scheme(_bars(["h", "h", "s", "s", "s"]), scheme)
    _assert(recent is not None and older is not None, "两例均应入选")
    _assert(
        float(recent["score"]) > float(older["score"]),
        f"更近的下影应排更高：{recent['score']} vs {older['score']}",
    )

    t0 = normalize_scheme(
        {
            "id": "t0_lower_shadow",
            "groups": [
                {
                    "id": "lower_shadow",
                    "days": [{"offset": 0, "lower_ratio_min": 0.35, "lower_ge_body": True}],
                }
            ],
        },
        trade_dates=TRADE_NEWEST_FIRST,
    )
    _assert(evaluate_scheme(_bars(["s", "s", "s", "s", "h"]), t0) is not None, "T0 收下影应入选")
    _assert(evaluate_scheme(_bars(["s", "s", "s", "h", "s"]), t0) is None, "仅 T-1 收下影不应入选 T0 方案")

    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
