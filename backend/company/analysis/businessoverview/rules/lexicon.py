"""业务词典：业务名称关键词 → 业务大类 / 赚钱模式 / 客群 / 白话模板 ID。

纯静态数据表，不含任何模型推断。命中与否完全由字符串匹配决定，
因此结果可复现、可审计、可解释。词典未命中时一律走 GENERIC 兜底模板。
"""

from __future__ import annotations

# 业务大类 → (赚钱模式模板 ID, 典型客群, 通俗一句话)
CATEGORY_LEXICON: dict[str, dict[str, str]] = {
    "白酒": {
        "category": "消费品-食品饮料",
        "model": "MAKE_THEN_SELL",
        "buyers": "经销商、商超和终端消费者",
        "product": "白酒产品",
    },
    "酒类": {
        "category": "消费品-食品饮料",
        "model": "MAKE_THEN_SELL",
        "buyers": "经销商和终端消费者",
        "product": "酒类产品",
    },
    "酒": {
        "category": "消费品-食品饮料",
        "model": "MAKE_THEN_SELL",
        "buyers": "经销商和终端消费者",
        "product": "酒类产品",
    },
    "食品": {"category": "消费品-食品饮料", "model": "MAKE_THEN_SELL",
             "buyers": "商超、经销商和消费者", "product": "食品"},
    "饮料": {"category": "消费品-食品饮料", "model": "MAKE_THEN_SELL",
             "buyers": "经销商和终端门店", "product": "饮料"},
    "家电": {"category": "消费品-家用电器", "model": "MAKE_THEN_SELL",
             "buyers": "经销商、电商与消费者", "product": "家电产品"},
    "服装": {"category": "消费品-纺织服饰", "model": "MAKE_THEN_SELL",
             "buyers": "品牌门店、经销商", "product": "服装"},
    "医药": {"category": "医药", "model": "MAKE_THEN_SELL",
             "buyers": "医院、药店和医药流通商", "product": "药品"},
    "原料药": {"category": "医药", "model": "MAKE_THEN_SELL",
               "buyers": "制药企业", "product": "原料药"},
    "疫苗": {"category": "医药", "model": "ORDER_EXECUTION",
             "buyers": "疾控中心和医院", "product": "疫苗"},
    "芯片": {"category": "科技-半导体", "model": "ORDER_EXECUTION",
             "buyers": "下游电子厂商", "product": "芯片"},
    "晶圆": {"category": "科技-半导体", "model": "ORDER_EXECUTION",
             "buyers": "芯片设计公司", "product": "晶圆"},
    "封装": {"category": "科技-半导体", "model": "ORDER_EXECUTION",
             "buyers": "芯片设计公司", "product": "封装服务"},
    "电子元件": {"category": "科技-电子", "model": "ORDER_EXECUTION",
                 "buyers": "整机厂商", "product": "电子元件"},
    "感知": {"category": "国防军工-电子信息化", "model": "PROJECT_DELIVERY",
             "buyers": "主机厂和军方科研院所", "product": "感知与探测装备"},
    "雷达": {"category": "国防军工-电子信息化", "model": "PROJECT_DELIVERY",
             "buyers": "主机厂和军方科研院所", "product": "雷达装备"},
    "装备": {"category": "国防军工", "model": "PROJECT_DELIVERY",
             "buyers": "军方和主机厂", "product": "装备产品"},
    "军品": {"category": "国防军工", "model": "PROJECT_DELIVERY",
             "buyers": "军方和主机厂", "product": "军品"},
    "军工": {"category": "国防军工", "model": "PROJECT_DELIVERY",
             "buyers": "军方和主机厂", "product": "军工产品"},
    "软件": {"category": "TMT-软件", "model": "PROJECT_DELIVERY",
             "buyers": "政府和企业客户", "product": "软件系统"},
    "系统集成": {"category": "TMT-计算机", "model": "PROJECT_DELIVERY",
                 "buyers": "政府和企业客户", "product": "系统集成项目"},
    "信息技术服务": {"category": "TMT-计算机", "model": "PROJECT_DELIVERY",
                     "buyers": "政府和企业客户", "product": "信息技术服务"},
    "通信": {"category": "TMT-通信", "model": "PROJECT_DELIVERY",
             "buyers": "运营商和企业客户", "product": "通信系统与服务"},
    "信息服务": {"category": "TMT-计算机", "model": "PROJECT_DELIVERY",
                 "buyers": "政府和企业客户", "product": "信息服务"},
    "工程施工": {"category": "建筑-工程", "model": "PROJECT_DELIVERY",
                 "buyers": "地方政府与业主方", "product": "工程项目"},
    "建筑": {"category": "建筑-工程", "model": "PROJECT_DELIVERY",
             "buyers": "地方政府与业主方", "product": "建筑施工"},
    "水泥": {"category": "建材", "model": "MAKE_THEN_SELL",
             "buyers": "经销商与施工方", "product": "水泥"},
    "房地产": {"category": "房地产", "model": "SELL_HOUSE",
               "buyers": "购房者和机构买家", "product": "商品房"},
    "风电": {"category": "新能源-发电", "model": "ASSET_YIELD",
             "buyers": "电网", "product": "风电场电量"},
    "光伏": {"category": "新能源-发电", "model": "ASSET_YIELD",
             "buyers": "电网", "product": "光伏电站电量"},
    "发电": {"category": "公用事业-电力", "model": "ASSET_YIELD",
             "buyers": "电网", "product": "上网电量"},
    "电力": {"category": "公用事业-电力", "model": "ASSET_YIELD",
             "buyers": "电网与工业用户", "product": "电力供应"},
    "供电": {"category": "公用事业-电力", "model": "ASSET_YIELD",
             "buyers": "电网与工业用户", "product": "供电服务"},
    "自来水": {"category": "公用事业", "model": "ASSET_YIELD",
               "buyers": "居民与工商业用户", "product": "供水"},
    "燃气": {"category": "公用事业", "model": "ASSET_YIELD",
             "buyers": "居民与工商业用户", "product": "燃气供应"},
    "旅游": {"category": "文旅", "model": "TICKET_ANCLINE",
             "buyers": "散客与旅行社", "product": "旅游服务"},
    "酒店": {"category": "文旅", "model": "TICKET_ANCLINE",
             "buyers": "散客与商务旅客", "product": "住宿服务"},
    "景区": {"category": "文旅", "model": "TICKET_ANCLINE",
             "buyers": "游客", "product": "景区门票与服务"},
    "教育": {"category": "社会服务-教育", "model": "SERVICE_SEASON",
             "buyers": "学生和家长", "product": "教育服务"},
    "电池": {"category": "新能源-制造", "model": "ORDER_EXECUTION",
             "buyers": "车企与储能集成商", "product": "动力电池"},
    "储能": {"category": "新能源-制造", "model": "ORDER_EXECUTION",
             "buyers": "储能集成商与电网", "product": "储能系统"},
    "汽车": {"category": "汽车", "model": "MAKE_THEN_SELL",
             "buyers": "经销商与消费者", "product": "整车"},
    "汽车零部件": {"category": "汽车", "model": "ORDER_EXECUTION",
                   "buyers": "整车厂商", "product": "汽车零部件"},
    "化工": {"category": "基础化工", "model": "MAKE_THEN_SELL",
             "buyers": "下游制造企业", "product": "化工产品"},
    "钢铁": {"category": "钢铁", "model": "MAKE_THEN_SELL",
             "buyers": "建筑与制造业客户", "product": "钢材"},
    "有色": {"category": "有色金属", "model": "MAKE_THEN_SELL",
             "buyers": "加工企业与贸易商", "product": "有色金属产品"},
    "采掘": {"category": "采掘", "model": "ASSET_YIELD",
             "buyers": "贸易商与加工企业", "product": "矿产资源"},
    "煤炭": {"category": "煤炭", "model": "ASSET_YIELD",
             "buyers": "电厂与贸易商", "product": "煤炭"},
    "石油": {"category": "石油石化", "model": "ASSET_YIELD",
             "buyers": "炼厂与贸易商", "product": "油气产品"},
    "农业": {"category": "农林牧渔", "model": "MAKE_THEN_SELL",
             "buyers": "经销商与加工厂", "product": "农产品"},
    "养殖": {"category": "农林牧渔", "model": "MAKE_THEN_SELL",
             "buyers": "屠宰加工商与经销商", "product": "畜禽产品"},
    "物流": {"category": "交通运输-物流", "model": "SERVICE_FEE",
             "buyers": "发货货主", "product": "物流运输服务"},
    "运输": {"category": "交通运输", "model": "SERVICE_FEE",
             "buyers": "货主与旅客", "product": "运输服务"},
    "银行": {"category": "金融-银行", "model": "SPREAD",
             "buyers": "存贷款客户", "product": "存贷款与中间业务"},
    "金融": {"category": "金融", "model": "SPREAD",
             "buyers": "存贷款与投资客户", "product": "金融服务"},
    "信贷": {"category": "金融-银行", "model": "SPREAD",
             "buyers": "企业客户", "product": "信贷服务"},
    "证券": {"category": "金融-证券", "model": "FEE_AND_SPREAD",
             "buyers": "投资者与发行人", "product": "经纪、投行与资管服务"},
    "保险": {"category": "金融-保险", "model": "PREMIUM_INVEST",
             "buyers": "投保人与被保险人", "product": "保险保障与投资"},
    "商业": {"category": "商贸零售", "model": "RESELL",
             "buyers": "终端消费者与企业客户", "product": "商品销售"},
    "零售": {"category": "商贸零售", "model": "RESELL",
             "buyers": "终端消费者", "product": "零售商品"},
}

# 通用兜底
GENERIC_CATEGORY = "未分类"
GENERIC_MODEL = "GENERIC"

# 模板 ID → 客群兜底
DEFAULT_BUYERS = "下游客户"

# 业务大类 → 商业模式一句话模板 ID
CATEGORY_MODEL_HINT: dict[str, str] = {
    "PROJECT_DELIVERY": "按项目/订单交付",
    "MAKE_THEN_SELL": "以销定产",
    "ORDER_EXECUTION": "按订单生产",
    "ASSET_YIELD": "重资产持续产出",
    "TICKET_ANCLINE": "客流变现",
    "SPREAD": "赚利差",
}

# 关键词 → 词典 key。key 即 CATEGORY_LEXICON 的键，也可用作展示名。
KEYWORD_INDEX: dict[str, str] = {kw: kw for kw in CATEGORY_LEXICON}


# 跨行业歧义词：单独看会误判（「零售金融」里的「零售」实为金融）。
# 键 = 歧义词，值 = 出现时必须同时命中的强信号词。
DISAMBIGUATING: dict[str, tuple[str, ...]] = {
    "零售": ("金融", "银行", "信贷", "保险", "证券", "支付"),
    "商业": ("金融", "地产"),
    "保险": ("代理",),
    "证券": ("承销",),
}


def lookup(name: str) -> dict[str, str] | None:
    """按业务名称精确/包含匹配词典，命中返回条目，否则 None。

    匹配顺序：
      1. 完全相等；
      2. 长关键词优先的包含匹配（避免「汽车零部件」被「汽车」抢走）；
      3. 歧义词需同时命中强信号词才生效（避免「零售金融」被当成商贸零售）。

    规则确定，无歧义；均未命中返回 None，由调用方走 GENERIC 兜底。
    """
    if not name:
        return None
    if name in CATEGORY_LEXICON:
        return {"keyword": name, **CATEGORY_LEXICON[name]}

    for kw in sorted(CATEGORY_LEXICON, key=len, reverse=True):
        if not kw or kw not in name:
            continue
        guards = DISAMBIGUATING.get(kw)
        if guards and not any(g in name for g in guards):
            continue
        return {"keyword": kw, **CATEGORY_LEXICON[kw]}
    return None