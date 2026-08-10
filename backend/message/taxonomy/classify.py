"""统一分类器：为单条信息打上 category / source_tier / subcategory。"""

from __future__ import annotations

from typing import Any

from .constants import (
    CATEGORY_COMPANY_IR,
    CATEGORY_DESIGNATED_PRESS,
    CATEGORY_DISCLOSURE,
    CATEGORY_MARKET_NEWS,
    CATEGORY_REGULATORY,
    CATEGORY_RESEARCH,
    REGULATORY_KINDS,
    STATUTORY_CHANNELS,
    TIER_BROKER,
    TIER_COMPANY_IR,
    TIER_DESIGNATED_PRESS,
    TIER_MARKET_MEDIA,
    TIER_PLATFORM,
    TIER_STATUTORY,
)
from .keywords import infer_subcategory
from .media_tiers import is_designated_press_media, resolve_media_tier


def _s(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        val = item.get(key)
        if val is None:
            continue
        text = str(val).strip()
        if text:
            return text
    return ""


def classify_item(item: dict[str, Any]) -> dict[str, Any]:
    """返回带分类标签的新字典，不修改入参。

    冲突规则：通道优先 > 媒体名单 > 标题关键词。
    """
    out = dict(item)
    channel = _s(item, "channel").lower()
    kind = _s(item, "kind").lower()
    source = _s(item, "source", "media_name", "mediaName")
    media = _s(item, "media_name", "mediaName", "source")
    title = _s(item, "title")
    paper = _s(item, "paper")
    outlet = _s(item, "outlet", "outlet_name")

    # --- category & source_tier ---
    category = CATEGORY_MARKET_NEWS
    tier = TIER_MARKET_MEDIA

    if kind == "report" or channel in {"report", "research"}:
        category = CATEGORY_RESEARCH
        tier = TIER_BROKER
    elif kind in REGULATORY_KINDS or channel == "regulatory":
        category = CATEGORY_REGULATORY
        tier = TIER_STATUTORY
    elif channel in STATUTORY_CHANNELS or kind == "notice":
        # 交易所/巨潮公告；若 kind 已是 inquiry/penalty 上面已处理
        if kind in REGULATORY_KINDS:
            category = CATEGORY_REGULATORY
        else:
            category = CATEGORY_DISCLOSURE
        tier = TIER_STATUTORY
    elif (
        channel in {"cs", "cnstock", "stcn", "zqrb", "financialnews", "jjckb", "chinadaily"}
        or kind == "press"
        or outlet
        or paper
        or is_designated_press_media(media)
        or is_designated_press_media(source)
    ):
        category = CATEGORY_DESIGNATED_PRESS
        tier = TIER_DESIGNATED_PRESS
    elif channel in {"company_ir", "ir"} or kind == "ir":
        category = CATEGORY_COMPANY_IR
        tier = TIER_COMPANY_IR
    elif kind == "news" or channel in {"news", "em", "eastmoney"}:
        category = CATEGORY_MARKET_NEWS
        tier = resolve_media_tier(media or source, default=TIER_MARKET_MEDIA)
        # 东财新闻若署名其实是指定报刊，升为 designated_press
        if tier == TIER_DESIGNATED_PRESS:
            category = CATEGORY_DESIGNATED_PRESS
        elif tier == TIER_PLATFORM:
            category = CATEGORY_MARKET_NEWS
    else:
        # 兜底：看媒体署名
        tier = resolve_media_tier(media or source, default=TIER_MARKET_MEDIA)
        if tier == TIER_DESIGNATED_PRESS:
            category = CATEGORY_DESIGNATED_PRESS
        elif tier == TIER_COMPANY_IR:
            category = CATEGORY_COMPANY_IR
        else:
            category = CATEGORY_MARKET_NEWS

    # --- subcategory ---
    if category == CATEGORY_REGULATORY:
        if kind == "inquiry":
            sub = "inquiry"
        elif kind == "penalty":
            sub = "penalty"
        else:
            sub = infer_subcategory(title, fallback="regulatory")
    elif category == CATEGORY_DISCLOSURE:
        sub = infer_subcategory(title, fallback="notice")
    elif category == CATEGORY_RESEARCH:
        sub = "research"
    elif category == CATEGORY_DESIGNATED_PRESS:
        sub = infer_subcategory(title, fallback="press")
    else:
        sub = infer_subcategory(title, fallback="news")

    out["category"] = category
    out["source_tier"] = tier
    out["subcategory"] = sub
    return out
