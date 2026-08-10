"""mediaName / source 字符串 → source_tier 映射。

未知来源默认 market_media；匹配采用「别名是否为来源子串」，
较长别名优先（在 resolve_media_tier 中处理）。
"""

from __future__ import annotations

from .constants import (
    TIER_BROKER,
    TIER_DESIGNATED_PRESS,
    TIER_MARKET_MEDIA,
    TIER_OFFICIAL_MEDIA,
    TIER_PLATFORM,
)

# (别名, tier) — 别名越具体越好
MEDIA_TIER_RULES: tuple[tuple[str, str], ...] = (
    # 指定披露七报七网
    ("中国证券报·中证金牛座", TIER_DESIGNATED_PRESS),
    ("中国证券报·中证网", TIER_DESIGNATED_PRESS),
    ("上海证券报·中国证券网", TIER_DESIGNATED_PRESS),
    ("中国证券报", TIER_DESIGNATED_PRESS),
    ("上海证券报", TIER_DESIGNATED_PRESS),
    ("证券时报网", TIER_DESIGNATED_PRESS),
    ("证券时报", TIER_DESIGNATED_PRESS),
    ("证券日报网", TIER_DESIGNATED_PRESS),
    ("证券日报", TIER_DESIGNATED_PRESS),
    ("经济参考报", TIER_DESIGNATED_PRESS),
    ("经济参考网", TIER_DESIGNATED_PRESS),
    ("金融时报", TIER_DESIGNATED_PRESS),
    ("中国金融新闻网", TIER_DESIGNATED_PRESS),
    ("中国日报网", TIER_DESIGNATED_PRESS),
    ("中国日报", TIER_DESIGNATED_PRESS),
    ("中证网", TIER_DESIGNATED_PRESS),
    ("中国证券网", TIER_DESIGNATED_PRESS),
    ("中证报", TIER_DESIGNATED_PRESS),
    ("上证报", TIER_DESIGNATED_PRESS),
    ("China Daily", TIER_DESIGNATED_PRESS),
    ("Chinadaily", TIER_DESIGNATED_PRESS),
    # 官方 / 央媒
    ("人民日报", TIER_OFFICIAL_MEDIA),
    ("人民网", TIER_OFFICIAL_MEDIA),
    ("人民财讯", TIER_OFFICIAL_MEDIA),
    ("经济日报", TIER_OFFICIAL_MEDIA),
    ("新华社", TIER_OFFICIAL_MEDIA),
    ("新华财经", TIER_OFFICIAL_MEDIA),
    ("中国新闻网", TIER_OFFICIAL_MEDIA),
    ("中新经纬", TIER_OFFICIAL_MEDIA),
    ("央视财经", TIER_OFFICIAL_MEDIA),
    ("央视新闻", TIER_OFFICIAL_MEDIA),
    ("央广财经", TIER_OFFICIAL_MEDIA),
    # 东财平台自有
    ("东方财富Choice数据", TIER_PLATFORM),
    ("东方财富研究中心", TIER_PLATFORM),
    ("东方财富证券", TIER_PLATFORM),
    ("东方财富", TIER_PLATFORM),
    ("数据宝", TIER_PLATFORM),
    ("e公司", TIER_PLATFORM),
    # 券商 / 期货机构
    ("广发证券", TIER_BROKER),
    ("中泰证券", TIER_BROKER),
    ("华金证券", TIER_BROKER),
    ("哈富证券", TIER_BROKER),
    ("金瑞期货", TIER_BROKER),
    ("瑞达期货", TIER_BROKER),
    ("券商中国", TIER_BROKER),
    # 市场化财经媒体（常见）
    ("财联社", TIER_MARKET_MEDIA),
    ("每日经济新闻", TIER_MARKET_MEDIA),
    ("界面新闻", TIER_MARKET_MEDIA),
    ("21世纪经济报道", TIER_MARKET_MEDIA),
    ("第一财经", TIER_MARKET_MEDIA),
    ("澎湃新闻", TIER_MARKET_MEDIA),
    ("科创板日报", TIER_MARKET_MEDIA),
    ("中国基金报", TIER_MARKET_MEDIA),
    ("中国经营报", TIER_MARKET_MEDIA),
    ("中国经营网", TIER_MARKET_MEDIA),
    ("国际金融报", TIER_MARKET_MEDIA),
    ("时代周报", TIER_MARKET_MEDIA),
    ("时代财经", TIER_MARKET_MEDIA),
    ("金融投资报", TIER_MARKET_MEDIA),
    ("北京商报", TIER_MARKET_MEDIA),
    ("深圳商报", TIER_MARKET_MEDIA),
    ("读创", TIER_MARKET_MEDIA),
    ("期货日报", TIER_MARKET_MEDIA),
    ("IPO日报", TIER_MARKET_MEDIA),
    ("南方都市报", TIER_MARKET_MEDIA),
    ("新京报", TIER_MARKET_MEDIA),
    ("上观新闻", TIER_MARKET_MEDIA),
    ("大河财立方", TIER_MARKET_MEDIA),
    ("红星资本局", TIER_MARKET_MEDIA),
    ("蓝鲸新闻", TIER_MARKET_MEDIA),
    ("蓝鲸财经", TIER_MARKET_MEDIA),
    ("新财富", TIER_MARKET_MEDIA),
    ("南方财经", TIER_MARKET_MEDIA),
    ("IT之家", TIER_MARKET_MEDIA),
)


def resolve_media_tier(media_or_source: str, default: str = TIER_MARKET_MEDIA) -> str:
    """按最长别名匹配 source_tier。"""
    text = (media_or_source or "").strip()
    if not text:
        return default
    best_tier = default
    best_len = -1
    for alias, tier in MEDIA_TIER_RULES:
        if alias in text and len(alias) > best_len:
            best_tier = tier
            best_len = len(alias)
    return best_tier


def is_designated_press_media(media_or_source: str) -> bool:
    return resolve_media_tier(media_or_source, default="") == TIER_DESIGNATED_PRESS
