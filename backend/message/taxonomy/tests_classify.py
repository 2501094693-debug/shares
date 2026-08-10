"""classify_item 样例断言（无网络）。

在 backend 目录::

    python -m message.taxonomy.tests_classify
"""

from __future__ import annotations

import sys

from message.taxonomy.classify import classify_item
from message.taxonomy.constants import (
    CATEGORY_DESIGNATED_PRESS,
    CATEGORY_DISCLOSURE,
    CATEGORY_MARKET_NEWS,
    CATEGORY_REGULATORY,
    CATEGORY_RESEARCH,
    TIER_BROKER,
    TIER_DESIGNATED_PRESS,
    TIER_MARKET_MEDIA,
    TIER_STATUTORY,
)


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def main() -> int:
    cases = [
        (
            {
                "title": "2025年年度报告",
                "channel": "cninfo",
                "kind": "notice",
                "source": "巨潮资讯",
            },
            CATEGORY_DISCLOSURE,
            TIER_STATUTORY,
            "periodic_report",
        ),
        (
            {
                "title": "公司收到深交所关注函",
                "channel": "szse",
                "kind": "inquiry",
                "source": "深圳证券交易所",
            },
            CATEGORY_REGULATORY,
            TIER_STATUTORY,
            "inquiry",
        ),
        (
            {
                "title": "贵州茅台股东大会召开",
                "channel": "stcn",
                "kind": "press",
                "source": "证券时报",
                "paper": "证券时报",
                "media_name": "证券时报网",
            },
            CATEGORY_DESIGNATED_PRESS,
            TIER_DESIGNATED_PRESS,
            "press",
        ),
        (
            {
                "title": "白酒板块早盘活跃",
                "channel": "news",
                "kind": "news",
                "source": "财联社",
                "media_name": "财联社",
            },
            CATEGORY_MARKET_NEWS,
            TIER_MARKET_MEDIA,
            "news",
        ),
        (
            {
                "title": "给予买入评级",
                "channel": "report",
                "kind": "report",
                "source": "某券商",
            },
            CATEGORY_RESEARCH,
            TIER_BROKER,
            "research",
        ),
        (
            {
                "title": "市场情绪逐步回暖",
                "channel": "news",
                "kind": "news",
                "source": "中国证券报",
                "media_name": "中国证券报",
            },
            CATEGORY_DESIGNATED_PRESS,
            TIER_DESIGNATED_PRESS,
            "press",
        ),
    ]

    for item, cat, tier, sub in cases:
        out = classify_item(item)
        _assert(out["category"] == cat, f"{item}: category {out['category']} != {cat}")
        _assert(out["source_tier"] == tier, f"{item}: tier {out['source_tier']} != {tier}")
        _assert(
            out["subcategory"] == sub,
            f"{item}: subcategory {out['subcategory']} != {sub}",
        )
        _assert(item.get("category") is None, "入参不应被原地修改")

    print("classify_item OK", len(cases), "cases")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print("FAIL:", exc, file=sys.stderr)
        raise SystemExit(1)
