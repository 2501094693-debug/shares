"""巨潮接口常量。"""

from datetime import timedelta, timezone

TZ_CN = timezone(timedelta(hours=8))

SEARCH_URL = "https://www.cninfo.com.cn/new/information/topSearch/query"
QUERY_URL = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
PDF_PREFIX = "https://static.cninfo.com.cn/"
PAGE_SIZE = 30
REQUEST_PAUSE_SEC = 0.25
MAX_PAGES = 50

# 静态股票表（含 orgId）。sse_stock.json 当前 404，深市这份可用作缓存。
STOCK_LIST_URLS = (
    "https://www.cninfo.com.cn/new/data/szse_stock.json",
)

SEARCH_PAGE = "https://www.cninfo.com.cn/new/commonUrl?url=disclosure/list/search"
HEADERS = {
    "Referer": SEARCH_PAGE,
    "Origin": "https://www.cninfo.com.cn",
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}
FORM_HEADERS = {
    **HEADERS,
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
}

# 市场栏目：上交所 sse / 深交所 szse / 北交所 bj
COLUMNS: dict[str, str] = {
    "sse": "sse",
    "sh": "sse",
    "szse": "szse",
    "sz": "szse",
    "bj": "bj",
    "bse": "bj",
    "auto": "auto",
}
COLUMN_BY_MARKET = {"sse": "sse", "szse": "szse", "bse": "bj"}

# fulltext 公告正文；relation 调研；supervise 持续督导
TABS: dict[str, str] = {
    "fulltext": "fulltext",
    "announcement": "fulltext",
    "notice": "fulltext",
    "公告": "fulltext",
    "relation": "relation",
    "ir": "relation",
    "调研": "relation",
    "supervise": "supervise",
    "督导": "supervise",
    "持续督导": "supervise",
}

# 板块过滤；查单股通常留空
PLATES: dict[str, str] = {
    "szmb": "深圳主板",
    "szcy": "创业板",
    "shmb": "上海主板",
    "shkcp": "科创板",
    "bj": "北交所",
}

# 沪深京公告分类。值是接口 category 字段；键是别名（可中英混用）。
CATEGORIES: dict[str, str] = {
    "annual": "category_ndbg_szsh",
    "年报": "category_ndbg_szsh",
    "ndbg": "category_ndbg_szsh",
    "semi": "category_bndbg_szsh",
    "半年报": "category_bndbg_szsh",
    "bndbg": "category_bndbg_szsh",
    "q1": "category_yjdbg_szsh",
    "一季报": "category_yjdbg_szsh",
    "yjdbg": "category_yjdbg_szsh",
    "q3": "category_sjdbg_szsh",
    "三季报": "category_sjdbg_szsh",
    "sjdbg": "category_sjdbg_szsh",
    "forecast": "category_yjygjxz_szsh",
    "业绩预告": "category_yjygjxz_szsh",
    "yjyg": "category_yjygjxz_szsh",
    "dividend": "category_qyfpxzcs_szsh",
    "权益分派": "category_qyfpxzcs_szsh",
    "board": "category_dshgg_szsh",
    "董事会": "category_dshgg_szsh",
    "supervisory": "category_jshgg_szsh",
    "监事会": "category_jshgg_szsh",
    "shareholder": "category_gddh_szsh",
    "股东大会": "category_gddh_szsh",
    "operation": "category_rcjy_szsh",
    "日常经营": "category_rcjy_szsh",
    "governance": "category_gszl_szsh",
    "公司治理": "category_gszl_szsh",
    "intermediary": "category_zj_szsh",
    "中介报告": "category_zj_szsh",
    "ipo": "category_sf_szsh",
    "首发": "category_sf_szsh",
    "seo": "category_zf_szsh",
    "增发": "category_zf_szsh",
    "equity": "category_gqbd_szsh",
    "股权变动": "category_gqbd_szsh",
    "unlock": "category_jj_szsh",
    "解禁": "category_jj_szsh",
    "cbond": "category_kzzq_szsh",
    "可转债": "category_kzzq_szsh",
    "rights": "category_pg_szsh",
    "配股": "category_pg_szsh",
    "other_financing": "category_qtrz_szsh",
    "其他融资": "category_qtrz_szsh",
    "incentive": "category_gqjl_szsh",
    "股权激励": "category_gqjl_szsh",
    "st": "category_tbclts_szsh",
    "特别处理": "category_tbclts_szsh",
    "delist": "category_tszlq_szsh",
    "退市整理": "category_tszlq_szsh",
    "amend": "category_bcgz_szsh",
    "补充更正": "category_bcgz_szsh",
}
