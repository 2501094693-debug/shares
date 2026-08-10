"""常量：接口地址、分页与监管关键词。"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

REQUEST_TIMEOUT = 30
REQUEST_PAUSE_SEC = 0.25
MAX_PAGES = 50
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# ---------------------------------------------------------------------------
# 巨潮
# ---------------------------------------------------------------------------

CNINFO_SEARCH_URL = "https://www.cninfo.com.cn/new/information/topSearch/query"
CNINFO_QUERY_URL = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
CNINFO_PDF_PREFIX = "https://static.cninfo.com.cn/"
CNINFO_PAGE_SIZE = 30  # 服务端硬限约 30

# ---------------------------------------------------------------------------
# 上交所
# ---------------------------------------------------------------------------

SSE_BULLETIN_URL = "https://query.sse.com.cn/security/stock/queryCompanyBulletin.do"
SSE_INQUIRE_URL = "https://query.sse.com.cn/commonSoaQuery.do"
SSE_PDF_PREFIX = "https://www.sse.com.cn"
SSE_PAGE_SIZE = 25
SSE_INQUIRE_PAGE_SIZE = 15
# 主板 A 股常用 securityType；科创板等若为空则回退巨潮 column=sse
SSE_SECURITY_TYPE_MAIN = "0101"
# 监管问询栏目（问询函 / 关注函 / 重组问询等）
SSE_INQUIRE_SQL_ID = "BS_KCB_GGLL"
SSE_INQUIRE_SITE_ID = "28"
SSE_INQUIRE_CHANNEL_IDS = "10743,10744,10012"

# ---------------------------------------------------------------------------
# 深交所
# ---------------------------------------------------------------------------

SZSE_ANN_URL = "https://www.szse.cn/api/disc/announcement/annList"
SZSE_INQUIRE_URL = "https://www.szse.cn/api/report/ShowReport/data"
SZSE_PDF_PREFIX = "https://disc.static.szse.cn"
SZSE_PAGE_SIZE = 50
SZSE_INQUIRE_CATALOG = "main_wxhj"
SZSE_INQUIRE_TABS = ("tab1", "tab2", "tab3")  # 主板 / 中小企业板 / 创业板等分区

# ---------------------------------------------------------------------------
# 北交所
# ---------------------------------------------------------------------------

BSE_ANN_URL = "https://www.bse.cn/disclosureInfoController/companyAnnouncement.do"
BSE_PDF_PREFIX = "https://www.bse.cn"
BSE_PAGE_SIZE = 20

# ---------------------------------------------------------------------------
# 监管关键词（公司披露的问询/处罚相关公告标题）
# ---------------------------------------------------------------------------

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
