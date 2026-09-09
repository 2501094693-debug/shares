"""磁盘缓存路径与 TTL 常量。"""

from __future__ import annotations

from pathlib import Path

# backend/cache（本文件在 backend/core/）
CACHE_DIR = Path(__file__).resolve().parents[1] / "cache"

CONS_CACHE_DIR = CACHE_DIR / "cons"
NEWS_CACHE_DIR = CACHE_DIR / "news"
LIST_CACHE_DIR = CACHE_DIR / "list"
FUND_LIST_CACHE_DIR = CACHE_DIR / "fund"
FUND_HOLDINGS_CACHE_DIR = CACHE_DIR / "fund" / "holdings"
OTC_FUND_CACHE_DIR = CACHE_DIR / "otc_fund"
OTC_FUND_INDEX_CACHE = CACHE_DIR / "otc_fund_index.json"
KLINE_CACHE_DIR = CACHE_DIR / "kline"
QUOTE_CACHE_DIR = CACHE_DIR / "quote"
STEEP_CACHE_DIR = CACHE_DIR / "steep"

TREE_CACHE = CACHE_DIR / "industry_tree.json"
STOCK_INDEX_CACHE = CACHE_DIR / "stocks_index.json"
CNINFO_ORG_MAP_CACHE = CACHE_DIR / "cninfo_org_map.json"
STOCK_GEO_CACHE = CACHE_DIR / "stock_geo.json"
FUND_TREE_CACHE = CACHE_DIR / "fund_tree.json"
FUND_INDEX_CACHE = CACHE_DIR / "fund_index.json"

# 成分股缓存有效期（秒）
CONS_TTL = 6 * 60 * 60
# 场内基金分类列表缓存有效期（秒）
FUND_LIST_TTL = 6 * 60 * 60
# 基金持仓 / 行业配置缓存有效期（秒）
FUND_HOLDINGS_TTL = 24 * 60 * 60
# 场外基金代码索引缓存有效期（秒）
OTC_FUND_INDEX_TTL = 24 * 60 * 60
# 场外基金分类排行缓存有效期（秒）
OTC_FUND_RANK_TTL = 60 * 60
# 注册地缓存有效期（秒）
GEO_TTL = 30 * 24 * 60 * 60


def ensure_cache_dirs() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CONS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    NEWS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    LIST_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    FUND_LIST_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    FUND_HOLDINGS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    OTC_FUND_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    KLINE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    QUOTE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    STEEP_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def otc_fund_rank_cache_path(category_code: str, page: int, page_size: int) -> Path:
    safe = category_code.strip().replace("/", "_")
    return OTC_FUND_CACHE_DIR / f"rank_{safe}_{page}_{page_size}.json"


def fund_list_cache_path(category_code: str) -> Path:
    """分类代码 → 场内基金列表缓存文件路径。"""
    safe = category_code.strip().replace("/", "_")
    return FUND_LIST_CACHE_DIR / f"{safe}.json"


def cons_cache_path(l3_code: str) -> Path:
    """三级行业代码 → 成分股缓存文件路径（`.` 替换为 `_`）。"""
    return CONS_CACHE_DIR / f"{l3_code.strip().replace('.', '_')}.json"
