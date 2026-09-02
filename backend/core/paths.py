"""磁盘缓存路径与 TTL 常量。"""

from __future__ import annotations

from pathlib import Path

# backend/cache（本文件在 backend/core/）
CACHE_DIR = Path(__file__).resolve().parents[1] / "cache"

CONS_CACHE_DIR = CACHE_DIR / "cons"
NEWS_CACHE_DIR = CACHE_DIR / "news"
LIST_CACHE_DIR = CACHE_DIR / "list"

TREE_CACHE = CACHE_DIR / "industry_tree.json"
STOCK_INDEX_CACHE = CACHE_DIR / "stocks_index.json"
STOCK_GEO_CACHE = CACHE_DIR / "stock_geo.json"

# 成分股缓存有效期（秒）
CONS_TTL = 6 * 60 * 60
# 注册地缓存有效期（秒）
GEO_TTL = 30 * 24 * 60 * 60


def ensure_cache_dirs() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CONS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    NEWS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    LIST_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def cons_cache_path(l3_code: str) -> Path:
    """三级行业代码 → 成分股缓存文件路径（`.` 替换为 `_`）。"""
    return CONS_CACHE_DIR / f"{l3_code.strip().replace('.', '_')}.json"
