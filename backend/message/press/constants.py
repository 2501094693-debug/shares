"""证监会指定披露媒体（七报七网）相关常量。"""

from __future__ import annotations

from typing import TypedDict


class Outlet(TypedDict):
    id: str
    name: str  # 网站常用名
    paper: str  # 报纸正式名
    domain: str
    home: str
    aliases: tuple[str, ...]  # 用于匹配 mediaName / 标题来源


# 对应证监会《具备证券市场信息披露条件的媒体名单》七家报纸及其官网
OUTLETS: tuple[Outlet, ...] = (
    {
        "id": "cs",
        "name": "中证网",
        "paper": "中国证券报",
        "domain": "cs.com.cn",
        "home": "https://www.cs.com.cn/",
        "aliases": ("中国证券报", "中证网", "中证报", "中国证券报中证网"),
    },
    {
        "id": "cnstock",
        "name": "中国证券网",
        "paper": "上海证券报",
        "domain": "cnstock.com",
        "home": "https://www.cnstock.com/",
        "aliases": ("上海证券报", "中国证券网", "上证报", "上海证券报中国证券网"),
    },
    {
        "id": "stcn",
        "name": "证券时报网",
        "paper": "证券时报",
        "domain": "stcn.com",
        "home": "https://www.stcn.com/",
        "aliases": ("证券时报", "证券时报网"),
    },
    {
        "id": "zqrb",
        "name": "证券日报网",
        "paper": "证券日报",
        "domain": "zqrb.cn",
        "home": "https://www.zqrb.cn/",
        "aliases": ("证券日报", "证券日报网"),
    },
    {
        "id": "financialnews",
        "name": "金融时报网",
        "paper": "金融时报",
        "domain": "financialnews.com.cn",
        "home": "https://www.financialnews.com.cn/",
        "aliases": ("金融时报", "中国金融新闻网", "金融新闻网"),
    },
    {
        "id": "jjckb",
        "name": "经济参考网",
        "paper": "经济参考报",
        "domain": "jjckb.cn",
        "home": "https://www.jjckb.cn/",
        "aliases": ("经济参考报", "经济参考网"),
    },
    {
        "id": "chinadaily",
        "name": "中国日报网",
        "paper": "中国日报",
        "domain": "chinadaily.com.cn",
        "home": "https://www.chinadaily.com.cn/",
        "aliases": ("中国日报", "中国日报网", "China Daily", "Chinadaily"),
    },
)

OUTLET_BY_ID = {o["id"]: o for o in OUTLETS}

EM_NEWS_URL = "https://search-api-web.eastmoney.com/search/jsonp"
EM_NEWS_CB = "jQuery35101792940631092459_1700000000000"
EM_PAGE_SIZE = 50
EM_MAX_PAGES = 8
REQUEST_PAUSE_SEC = 0.25
