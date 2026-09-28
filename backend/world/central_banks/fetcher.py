"""主要国家央行利率数据获取。

支持多数据源，按优先级自动选择：
1. 东方财富 (eastmoney) - 优先级最高，数据最全面
2. 新浪财经 (sina) - 实时数据
3. 腾讯证券 (tencent) - 备用数据源
4. 雪球 (xueqiu) - 社区数据
5. 金10数据 (jin10) - 财经日历
6. 静态数据 (static) - 备用/兜底
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Any

from core.http import browser_get, get_json, get_text

from world.central_banks.catalog import CENTRAL_BANKS, STATIC_RATES

logger = logging.getLogger(__name__)

# =============================================================================
# 东方财富 API
# =============================================================================
_EASTMONEY_BASE = "https://datacenter-web.eastmoney.com/api/data/v1/get"
_EASTMONEY_HEADERS = {
    "Referer": "https://data.eastmoney.com/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}


def _fetch_eastmoney_lpr(*, limit: int) -> list[dict[str, Any]]:
    """从东方财富获取中国LPR数据。"""
    params = {
        "reportName": "RPTA_WEB_RATE",
        "columns": "TRADE_DATE,LPR1Y,LPR5Y,RATE_1,RATE_2",
        "sortColumns": "TRADE_DATE",
        "sortTypes": "-1",
        "pageNumber": "1",
        "pageSize": str(limit),
        "source": "WEB",
        "client": "WEB",
    }
    try:
        resp = get_json(_EASTMONEY_BASE, params=params, headers=_EASTMONEY_HEADERS, timeout=15)
        rows = (resp.get("result") or {}).get("data") or []
        out = []
        for row in rows:
            date = str(row.get("TRADE_DATE") or "")[:10]
            out.append({
                "date": date,
                "value": _num(row.get("LPR1Y")),
                "lpr_5y": _num(row.get("LPR5Y")),
                "forecast": None,
                "previous": None,
            })
        return out
    except Exception as exc:
        logger.warning("[eastmoney] LPR获取失败: %s", exc)
        return []


def _fetch_eastmoney_hibor(*, limit: int) -> list[dict[str, Any]]:
    """从东方财富获取香港HIBOR数据。"""
    params = {
        "reportName": "RPT_IMP_INTRESTRATEN",
        "columns": "REPORT_DATE,IR_RATE,CHANGE_RATE",
        'filter': '(MARKET_CODE="005")(CURRENCY_CODE="HKD")(INDICATOR_ID="203")',
        "pageNumber": "1",
        "pageSize": str(limit),
        "sortTypes": "-1",
        "sortColumns": "REPORT_DATE",
        "source": "WEB",
        "client": "WEB",
    }
    try:
        resp = get_json(_EASTMONEY_BASE, params=params, headers=_EASTMONEY_HEADERS, timeout=12)
        rows = (resp.get("result") or {}).get("data") or []
        out = []
        for row in rows:
            out.append({
                "date": str(row.get("REPORT_DATE") or "")[:10],
                "value": _num(row.get("IR_RATE")),
                "change_bp": _num(row.get("CHANGE_RATE")),
                "forecast": None,
                "previous": None,
            })
        return out
    except Exception as exc:
        logger.warning("[eastmoney] HIBOR获取失败: %s", exc)
        return []


def _fetch_eastmoney_federal_funds(*, limit: int) -> list[dict[str, Any]]:
    """从东方财富获取美联储联邦基金利率。"""
    # 东方财富没有直接的联邦基金利率数据，用替代方案
    # 通过东方财富宏观数据API获取
    params = {
        "reportName": "RPTA_WEB_MACRO_DATA",
        "columns": "REPORT_DATE,COUNTRY,INDICATOR_ID,INDICATOR_NAME,DATA_VALUE,PREV_VALUE,CHANGE_RATE",
        'filter': '(INDICATOR_ID="USFFRATE")(COUNTRY="美国")',
        "pageNumber": "1",
        "pageSize": str(limit),
        "sortTypes": "-1",
        "sortColumns": "REPORT_DATE",
        "source": "WEB",
        "client": "WEB",
    }
    try:
        resp = get_json(_EASTMONEY_BASE, params=params, headers=_EASTMONEY_HEADERS, timeout=15)
        rows = (resp.get("result") or {}).get("data") or []
        out = []
        for row in rows:
            out.append({
                "date": str(row.get("REPORT_DATE") or "")[:10],
                "value": _num(row.get("DATA_VALUE")),
                "forecast": None,
                "previous": _num(row.get("PREV_VALUE")),
            })
        return out
    except Exception as exc:
        logger.warning("[eastmoney] 联邦基金利率获取失败: %s", exc)
        return []


# =============================================================================
# 新浪财经 API
# =============================================================================
_SINA_BASE = "https://money.finance.sina.com.cn"
_SINA_MONEY_API = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php"


def _fetch_sina_federal_funds(*, limit: int) -> list[dict[str, Any]]:
    """从新浪财经获取美联储利率数据。"""
    # 新浪宏观数据API
    url = f"{_SINA_MONEY_API}/M_CFB_MacroData"
    params = {
        "type": "USFFRATE",
        "page": "1",
        "num": str(limit),
        "sort": "date",
        "asc": "0",
    }
    try:
        text = get_text(url, params=params, timeout=12)
        # 解析JSONP格式
        match = re.search(r'\((.*)\)', text, re.S)
        if match:
            import json
            data = json.loads(match.group(1))
            rows = data.get("data", []) if isinstance(data, dict) else []
            out = []
            for row in rows[:limit]:
                if isinstance(row, dict):
                    out.append({
                        "date": str(row.get("date", ""))[:10],
                        "value": _num(row.get("rate")),
                        "forecast": _num(row.get("forecast")),
                        "previous": _num(row.get("previous")),
                    })
            return out
        return []
    except Exception as exc:
        logger.warning("[sina] 联邦基金利率获取失败: %s", exc)
        return []


def _fetch_sina_lpr(*, limit: int) -> list[dict[str, Any]]:
    """从新浪财经获取中国LPR数据。"""
    # 新浪LPR利率接口
    url = "https://hq.sinajs.cn/list=gb_lpr1y,gb_lpr5y"
    try:
        text = get_text(url, params={}, timeout=10, encoding="gbk")
        out = []
        # 解析格式: var hq_str_gb_lpr1y="2026-09-20,3.35,3.35,3.35";
        for m in re.finditer(r'hq_str_gb_(\w+)=\"([^\"]+)\"', text):
            rate_type = m.group(1)  # lpr1y 或 lpr5y
            vals = m.group(2).split(",")
            if len(vals) >= 2:
                date_str = vals[0].strip()
                current = _num(vals[1])
                out.append({
                    "date": date_str,
                    "value": current,
                    "lpr_5y": _num(vals[2]) if rate_type == "lpr1y" and len(vals) > 2 else None,
                    "forecast": None,
                    "previous": None,
                })
        return out[:limit]
    except Exception as exc:
        logger.warning("[sina] LPR获取失败: %s", exc)
        return []


# =============================================================================
# 腾讯证券 API
# =============================================================================
_TENCENT_BASE = "https://web.ifzq.gtimg.cn"
_TENCENT_APPID = "2"


def _fetch_tencent_central_bank(region: str, *, limit: int) -> list[dict[str, Any]]:
    """从腾讯获取各国央行利率数据。"""
    # 腾讯宏观数据接口
    region_map = {
        "us": "US",
        "eu": "EU",
        "cn": "CN",
        "jp": "JP",
        "uk": "UK",
        "ca": "CA",
        "au": "AU",
        "nz": "NZ",
    }
    country = region_map.get(region, region.upper())
    
    url = f"{_TENCENT_BASE}/appstock/app/rate/getRateData"
    params = {
        "country": country,
        "type": "rate",
        "_var": f"rate_{region}",
        "count": str(limit),
    }
    try:
        text = get_text(url, params=params, timeout=12)
        # 解析JSONP格式
        match = re.search(r'=(\{.*\})', text, re.S)
        if match:
            import json
            data = json.loads(match.group(1))
            items = data.get("data", {}).get("list", []) if isinstance(data, dict) else []
            out = []
            for item in items:
                if isinstance(item, dict):
                    out.append({
                        "date": str(item.get("date", ""))[:10],
                        "value": _num(item.get("rate")),
                        "forecast": _num(item.get("forecast")),
                        "previous": _num(item.get("prevRate")),
                    })
            return out
        return []
    except Exception as exc:
        logger.warning("[tencent] %s 利率获取失败: %s", region, exc)
        return []


def _fetch_tencent_hibor(*, limit: int) -> list[dict[str, Any]]:
    """从腾讯获取香港HIBOR数据。"""
    url = f"{_TENCENT_BASE}/appstock/app/quotation/getMingxi"
    params = {
        "param": "hkHIBOR,n,d,,,10",
        "_var": "hkhibor_detail",
    }
    try:
        text = get_text(url, params=params, timeout=10)
        match = re.search(r'=(\{.*\})', text, re.S)
        if match:
            import json
            data = json.loads(match.group(1))
            items = data.get("data", {}).get("hkHIBOR", {}).get("datas", []) if isinstance(data, dict) else []
            out = []
            for item in items[:limit]:
                if isinstance(item, dict):
                    out.append({
                        "date": str(item.get("date", ""))[:10],
                        "value": _num(item.get("close")),
                        "forecast": None,
                        "previous": None,
                    })
            return out
        return []
    except Exception as exc:
        logger.warning("[tencent] HIBOR获取失败: %s", exc)
        return []


# =============================================================================
# 雪球 API
# =============================================================================
_XUEQIU_BASE = "https://stock.xueqiu.com"
_XUEQIU_HEADERS = {
    "Referer": "https://xueqiu.com/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}


def _fetch_xueqiu_rate(region: str, *, limit: int) -> list[dict[str, Any]]:
    """从雪球获取各国央行利率数据。"""
    # 雪球宏观数据接口
    symbol_map = {
        "us": "USFFRATE",    # 美联储联邦基金利率
        "eu": "ECBMAINRATE", # 欧洲央行主要利率
        "cn": "CNLPR1Y",     # 中国1年期LPR
        "jp": "JPBOJRATE",   # 日本央行利率
        "uk": "UKBOERATE",   # 英国央行利率
        "ca": "CABOCRATE",   # 加拿大央行利率
        "au": "AURBARATE",   # 澳大利亚央行利率
    }
    symbol = symbol_map.get(region, f"{region.upper()}RATE")
    
    url = f"{_XUEQIU_BASE}/v5/stock/chart/macro.json"
    params = {
        "symbol": symbol,
        "type": "Q",
        "period": "M",
        "count": f"-{limit}",
    }
    try:
        resp_json = get_json(url, params=params, headers=_XUEQIU_HEADERS, timeout=15)
        items = resp_json.get("data", {}).get("items", []) if isinstance(resp_json, dict) else []
        out = []
        for item in items:
            if isinstance(item, dict):
                out.append({
                    "date": str(item.get("date", ""))[:10],
                    "value": _num(item.get("value")),
                    "forecast": None,
                    "previous": None,
                })
        return out
    except Exception as exc:
        logger.warning("[xueqiu] %s 利率获取失败: %s", region, exc)
        return []


# =============================================================================
# 金10数据 API
# =============================================================================
_JIN10_URL = "https://datacenter-api.jin10.com/reports/list_v2"
_JIN10_HEADERS = {
    "x-app-id": "rU6QIu7JHe2gOUeR",
    "x-version": "1.0.0",
    "Origin": "https://datacenter.jin10.com",
    "Referer": "https://datacenter.jin10.com/",
}


def _fetch_jin10(attr_id: str, *, limit: int) -> list[dict[str, Any]]:
    """从金10数据中心获取利率数据。"""
    rows: list[list[Any]] = []
    max_date = ""
    attempt = 0
    while len(rows) < limit and attempt < 5:
        attempt += 1
        params = {
            "max_date": max_date,
            "category": "ec",
            "attr_id": attr_id,
            "_": str(int(datetime.now().timestamp() * 1000)),
        }
        try:
            resp = get_json(_JIN10_URL, params=params, headers=_JIN10_HEADERS, timeout=12)
            vals = (resp.get("data", {}) or {}).get("values") or []
        except Exception as exc:
            logger.warning("[jin10] attr_id=%s 请求失败: %s", attr_id, exc)
            break
        if not vals:
            logger.debug("[jin10] attr_id=%s 第%d次尝试返回空数据", attr_id, attempt)
            break
        rows.extend(vals)
        last = vals[-1][0]
        try:
            max_date = (
                datetime.strptime(str(last), "%Y-%m-%d").date() - timedelta(days=1)
            ).isoformat()
        except ValueError:
            break
        if len(vals) < 20:
            break

    if not rows:
        logger.warning("[jin10] attr_id=%s 未获取到任何数据", attr_id)

    out: list[dict[str, Any]] = []
    for item in rows[:limit]:
        if not item or len(item) < 4:
            continue
        out.append({
            "date": str(item[0]),
            "value": _num(item[1]),
            "forecast": _num(item[2]),
            "previous": _num(item[3]),
        })
    return out


def _fetch_jin10_bok(*, limit: int) -> list[dict[str, Any]]:
    """从金10获取韩国央行利率。"""
    return _fetch_jin10("3015", limit=limit)  # 韩国利率 attr_id


# =============================================================================
# 韩国央行直接获取
# =============================================================================
_BOK_URL = (
    "https://www.bok.or.kr/portal/singl/baseRate/list.do"
    "?dataSeCd=01&menuNo=200068"
)


def _fetch_bok(*, limit: int) -> list[dict[str, Any]]:
    """从韩国央行官网获取基准利率。"""
    html = browser_get(_BOK_URL, timeout=20).text
    match = re.search(r"var\s+chartObj2_s\s*=\s*(\[\[.*?\]\])", html, re.S)
    if not match:
        return []
    raw = match.group(1)
    pairs = re.findall(r'\[\s*"([^"]+)"\s*,\s*([0-9.]+)\s*\]', raw)
    rows: list[dict[str, Any]] = []
    for date_raw, value in pairs:
        date = date_raw.strip().replace("/", "-").split()[0]
        rows.append({
            "date": date,
            "value": _num(value),
            "forecast": None,
            "previous": None,
        })
    rows.reverse()
    return rows[:limit]


# =============================================================================
# 静态数据 (兜底)
# =============================================================================
def _fetch_static(region: str, *, limit: int) -> list[dict[str, Any]]:
    """静态利率数据 (备用数据源)。"""
    if region not in STATIC_RATES:
        logger.warning("[static] region=%s 无静态数据", region)
        return []
    history: list[dict[str, Any]] = []
    for date, value in STATIC_RATES[region][:limit]:
        history.append({
            "date": date,
            "value": value,
            "forecast": None,
            "previous": None,
        })
    return history


# =============================================================================
# 工具函数
# =============================================================================
def _num(raw: Any) -> float | None:
    """安全转换为浮点数。"""
    if raw is None or raw == "":
        return None
    try:
        return round(float(raw), 4)
    except (TypeError, ValueError):
        return None


# =============================================================================
# 数据源优先级配置
# =============================================================================
# 每个国家/地区的数据源优先级列表，按顺序尝试
_SOURCE_PRIORITIES: dict[str, list[str]] = {
    "us": ["tencent", "sina", "eastmoney", "xueqiu", "jin10", "static"],
    "eu": ["tencent", "sina", "xueqiu", "static"],
    "cn": ["eastmoney", "sina", "xueqiu", "static"],
    "jp": ["tencent", "sina", "xueqiu", "static"],
    "uk": ["tencent", "sina", "xueqiu", "static"],
    "ca": ["tencent", "sina", "xueqiu", "static"],
    "au": ["tencent", "sina", "xueqiu", "static"],
    "nz": ["tencent", "sina", "xueqiu", "static"],
    "kr": ["bok", "jin10", "tencent", "static"],
    "in": ["tencent", "sina", "static"],
    "br": ["tencent", "sina", "static"],
    "mx": ["tencent", "sina", "static"],
    "za": ["tencent", "sina", "static"],
    "ru": ["tencent", "sina", "static"],
    "se": ["tencent", "sina", "static"],
    "no": ["tencent", "sina", "static"],
    "ch": ["tencent", "sina", "static"],
    "hk": ["eastmoney", "tencent", "static"],
}

# 数据源获取函数映射
_SOURCE_FETCHERS: dict[str, callable] = {
    "eastmoney": {
        "cn": lambda **kw: _fetch_eastmoney_lpr(**kw),
        "hk": lambda **kw: _fetch_eastmoney_hibor(**kw),
        "us": lambda **kw: _fetch_eastmoney_federal_funds(**kw),
    },
    "sina": {
        "cn": lambda **kw: _fetch_sina_lpr(**kw),
        "us": lambda **kw: _fetch_sina_federal_funds(**kw),
    },
    "tencent": {
        "default": lambda region, **kw: _fetch_tencent_central_bank(region, **kw),
        "hk": lambda **kw: _fetch_tencent_hibor(**kw),
    },
    "xueqiu": {
        "default": lambda region, **kw: _fetch_xueqiu_rate(region, **kw),
    },
    "jin10": {
        "kr": lambda **kw: _fetch_jin10_bok(**kw),
    },
    "bok": {
        "kr": lambda **kw: _fetch_bok(**kw),
    },
    "static": {
        "default": lambda region, **kw: _fetch_static(region, **kw),
    },
}


def _fetch_with_source(region: str, source: str, *, limit: int) -> tuple[list[dict[str, Any]], str]:
    """使用指定数据源获取利率数据。
    
    Returns:
        (数据列表, 实际使用的数据源)
    """
    # 特殊处理的数据源
    if source in _SOURCE_FETCHERS:
        fetchers = _SOURCE_FETCHERS[source]
        
        # 先尝试 region 特定函数
        if region in fetchers:
            try:
                data = fetchers[region](limit=limit)
                if data:
                    return data, source
            except Exception as exc:
                logger.debug("[%s] %s 特定获取失败: %s", source, region, exc)
        
        # 再尝试默认函数
        default = fetchers.get("default")
        if default:
            try:
                data = default(region=region, limit=limit)
                if data:
                    return data, source
            except Exception as exc:
                logger.debug("[%s] %s 默认获取失败: %s", source, region, exc)
    
    return [], source


def fetch_central_bank_series(region: str, *, limit: int = 60) -> dict[str, Any]:
    """获取央行利率数据，按优先级自动选择数据源。
    
    Args:
        region: 地区代码 (us, eu, cn, etc.)
        limit: 获取历史数据条数
        
    Returns:
        包含最新利率和历史数据的字典
    """
    cfg = CENTRAL_BANKS[region]
    priorities = _SOURCE_PRIORITIES.get(region, ["static"])
    
    history: list[dict[str, Any]] = []
    used_source = "static"
    
    # 按优先级尝试各数据源
    for source in priorities:
        data, actual_source = _fetch_with_source(region, source, limit=limit)
        if data:
            history = data
            used_source = actual_source
            logger.info("[利率] region=%s 使用数据源: %s", region, used_source)
            break
    else:
        logger.warning("[利率] region=%s 所有数据源均未获取到数据", region)
    
    latest = history[0] if history else {}

    return {
        "region": region,
        "name": cfg["name"],
        "bank_name": cfg["bank_name"],
        "rate_name": cfg["rate_name"],
        "source": used_source,
        "description": cfg["description"],
        "latest": latest,
        "history": history,
    }


def fetch_central_banks(*, limit: int = 60, regions: list[str] | None = None) -> dict[str, Any]:
    """批量获取多个央行利率数据。
    
    Args:
        limit: 获取历史数据条数
        regions: 指定地区列表，None 表示全部
        
    Returns:
        包含所有央行数据的字典
    """
    keys = regions or list(CENTRAL_BANKS.keys())
    items = [fetch_central_bank_series(region, limit=limit) for region in keys]
    return {"items": items}
