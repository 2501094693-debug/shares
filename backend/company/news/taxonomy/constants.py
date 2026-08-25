"""统一信息分类枚举。"""

from __future__ import annotations

from typing import Final

CATEGORY_DISCLOSURE: Final = "disclosure"
CATEGORY_REGULATORY: Final = "regulatory"
CATEGORY_DESIGNATED_PRESS: Final = "designated_press"
CATEGORY_MARKET_NEWS: Final = "market_news"
CATEGORY_RESEARCH: Final = "research"
CATEGORY_COMPANY_IR: Final = "company_ir"

CATEGORIES: tuple[str, ...] = (
    CATEGORY_DISCLOSURE,
    CATEGORY_REGULATORY,
    CATEGORY_DESIGNATED_PRESS,
    CATEGORY_MARKET_NEWS,
    CATEGORY_RESEARCH,
    CATEGORY_COMPANY_IR,
)

TIER_STATUTORY: Final = "statutory"
TIER_DESIGNATED_PRESS: Final = "designated_press"
TIER_OFFICIAL_MEDIA: Final = "official_media"
TIER_MARKET_MEDIA: Final = "market_media"
TIER_BROKER: Final = "broker"
TIER_PLATFORM: Final = "platform"
TIER_COMPANY_IR: Final = "company_ir"

SOURCE_TIERS: tuple[str, ...] = (
    TIER_STATUTORY,
    TIER_DESIGNATED_PRESS,
    TIER_OFFICIAL_MEDIA,
    TIER_MARKET_MEDIA,
    TIER_BROKER,
    TIER_PLATFORM,
    TIER_COMPANY_IR,
)

SECTION_DISCLOSURE: Final = "disclosure"
SECTION_REGULATORY: Final = "regulatory"
SECTION_DESIGNATED_PRESS: Final = "designated_press"
SECTION_MARKET_NEWS: Final = "market_news"
SECTION_RESEARCH: Final = "research"

DEFAULT_SECTIONS: tuple[str, ...] = (
    SECTION_DISCLOSURE,
    SECTION_REGULATORY,
    SECTION_DESIGNATED_PRESS,
)

ALL_SECTIONS: tuple[str, ...] = (
    SECTION_DISCLOSURE,
    SECTION_REGULATORY,
    SECTION_DESIGNATED_PRESS,
    SECTION_MARKET_NEWS,
    SECTION_RESEARCH,
)

STATUTORY_CHANNELS: frozenset[str] = frozenset(
    {"sse", "szse", "bse", "cninfo", "regulatory", "bulletin"}
)

REGULATORY_KINDS: frozenset[str] = frozenset(
    {"inquiry", "penalty", "regulatory"}
)

REGULATORY_TITLE_KEYWORDS: tuple[str, ...] = (
    "问询函",
    "关注函",
    "监管函",
    "警示函",
    "责令改正",
    "监管措施",
    "纪律处分",
    "通报批评",
    "公开谴责",
    "行政处罚",
    "市场禁入",
    "立案告知",
    "立案调查",
    "处罚决定",
    "监管工作函",
)

PRESS_OUTLETS: tuple[dict[str, str], ...] = (
    {"id": "cs", "name": "中证网", "paper": "中国证券报"},
    {"id": "cnstock", "name": "中国证券网", "paper": "上海证券报"},
    {"id": "stcn", "name": "证券时报网", "paper": "证券时报"},
    {"id": "zqrb", "name": "证券日报网", "paper": "证券日报"},
    {"id": "financialnews", "name": "金融时报网", "paper": "金融时报"},
    {"id": "jjckb", "name": "经济参考网", "paper": "经济参考报"},
    {"id": "chinadaily", "name": "中国日报网", "paper": "中国日报"},
)

PRESS_OUTLET_IDS: tuple[str, ...] = tuple(o["id"] for o in PRESS_OUTLETS)
