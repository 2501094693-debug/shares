"""巨潮资讯网公告。

官网查询页：https://www.cninfo.com.cn/new/commonUrl?url=disclosure/list/search

不能只传 6 位代码。列表接口的 ``stock`` 必须是 ``代码,orgId``。
``fetch_announcements`` 固定三步：params → request → parse。

    python -m company.news.official.cninfo.cli 600519
    python -m company.news.official.cninfo.cli 600519 --days 90 --category annual
    python -m company.news.official.cninfo.cli 600519 --keyword 问询函
    python -m company.news.official.cninfo.cli 600519 --tab relation
    python -m company.news.official.cninfo.cli 600519 --org-only
    python -m company.news.official.cninfo.cli 000001 --download ./pdfs --limit 3
    python -m company.news.official.cninfo.cli --market szse --category annual --days 30 --limit 20
"""

from company.news.official.cninfo.cli import main
from company.news.official.cninfo.constants import CATEGORIES, COLUMNS, PLATES, TABS
from company.news.official.cninfo.fetch import (
    fetch_announcements,
    fetch_market_announcements,
    fetch_periodic_reports,
    fetch_supervise,
    fetch_surveys,
    search_announcements,
)
from company.news.official.cninfo.params import (
    a_share_code,
    resolve_category,
    resolve_column,
    resolve_org,
    resolve_tab,
)
from company.news.official.cninfo.parse import parse_announcement_time, pdf_url, strip_em
from company.news.official.cninfo.request import (
    download_announcements,
    download_pdf,
    load_org_map,
    query_page,
    search_orgs,
)

__all__ = [
    "CATEGORIES",
    "COLUMNS",
    "PLATES",
    "TABS",
    "a_share_code",
    "download_announcements",
    "download_pdf",
    "fetch_announcements",
    "fetch_market_announcements",
    "fetch_periodic_reports",
    "fetch_supervise",
    "fetch_surveys",
    "load_org_map",
    "main",
    "parse_announcement_time",
    "pdf_url",
    "query_page",
    "resolve_category",
    "resolve_column",
    "resolve_org",
    "resolve_tab",
    "search_announcements",
    "search_orgs",
    "strip_em",
]
