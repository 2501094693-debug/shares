"""统一信息分类枚举。"""

from __future__ import annotations

from typing import Final

# 业务大类
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

# 信源层级（可信度从高到低大致递减）
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

# profile 可采集的 section 名（与 groups 键对齐，另含采集开关）
SECTION_DISCLOSURE: Final = "disclosure"
SECTION_REGULATORY: Final = "regulatory"
SECTION_DESIGNATED_PRESS: Final = "designated_press"
SECTION_MARKET_NEWS: Final = "market_news"
SECTION_RESEARCH: Final = "research"

# 默认只采法定与指定报刊，避免全量过慢；news/reports 需显式打开
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

# 法定披露通道
STATUTORY_CHANNELS: frozenset[str] = frozenset(
    {"sse", "szse", "bse", "cninfo", "regulatory"}
)

# 监管类 kind
REGULATORY_KINDS: frozenset[str] = frozenset(
    {"inquiry", "penalty", "regulatory"}
)
