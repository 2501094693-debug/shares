"""原油品种目录。"""

from __future__ import annotations

# source:
#   sina_hf  — 新浪外盘期货 hq.sinajs.cn/list=hf_*（布伦特 / WTI）
#   sina_nf  — 新浪国内期货 hq.sinajs.cn/list=nf_*（上海原油）
#   oilprice — oilprice.com 实货/评估价（迪拜 / 阿曼 / 乌拉尔，同源可比）
OIL: list[dict[str, str]] = [
    {"id": "brent", "name": "布伦特原油", "source": "sina_hf", "symbol": "hf_OIL"},
    {"id": "wti", "name": "美国原油(WTI)", "source": "sina_hf", "symbol": "hf_CL"},
    {"id": "dubai", "name": "迪拜原油", "source": "oilprice", "blend_id": "144"},
    {"id": "oman", "name": "阿曼原油", "source": "oilprice", "blend_id": "48"},
    {"id": "shanghai", "name": "上海原油", "source": "sina_nf", "symbol": "nf_SC0"},
    {"id": "urals", "name": "乌拉尔原油", "source": "oilprice", "blend_id": "4466"},
]
