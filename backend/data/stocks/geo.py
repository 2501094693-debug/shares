"""上市公司注册地 enrich。

职责（后端只做文本侧）：
1. 从东财 F10 拉公司全称、注册地址、区域；
2. 解析规范省 / 市名；
3. 磁盘缓存，供批量 enrich。

经纬度由前端高德 PlaceSearch（公司全称）标注，本模块不负责算坐标。
对外入口：enrich_codes() ← POST /api/stocks/geo-enrich
"""

from __future__ import annotations

import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from data.core.paths import GEO_TTL, STOCK_GEO_CACHE, ensure_cache_dirs
from message.disclosure.http_util import detect_market, http_get, normalize_code, safe_str

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

_EM_SURVEY_URL = (
    "https://emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/CompanySurveyAjax"
)

_CITY_CENTROIDS_PATH = (
    Path(__file__).resolve().parents[3]
    / "frontend"
    / "shared"
    / "geo"
    / "city-centroids.json"
)

_PROVINCES: tuple[str, ...] = (
    "北京市",
    "天津市",
    "河北省",
    "山西省",
    "内蒙古自治区",
    "辽宁省",
    "吉林省",
    "黑龙江省",
    "上海市",
    "江苏省",
    "浙江省",
    "安徽省",
    "福建省",
    "江西省",
    "山东省",
    "河南省",
    "湖北省",
    "湖南省",
    "广东省",
    "广西壮族自治区",
    "海南省",
    "重庆市",
    "四川省",
    "贵州省",
    "云南省",
    "西藏自治区",
    "陕西省",
    "甘肃省",
    "青海省",
    "宁夏回族自治区",
    "新疆维吾尔自治区",
    "香港特别行政区",
    "澳门特别行政区",
    "台湾省",
)

_PROVINCE_ALIASES: dict[str, str] = {
    "北京": "北京市",
    "天津": "天津市",
    "河北": "河北省",
    "山西": "山西省",
    "内蒙古": "内蒙古自治区",
    "内蒙": "内蒙古自治区",
    "辽宁": "辽宁省",
    "吉林": "吉林省",
    "黑龙江": "黑龙江省",
    "上海": "上海市",
    "江苏": "江苏省",
    "浙江": "浙江省",
    "安徽": "安徽省",
    "福建": "福建省",
    "江西": "江西省",
    "山东": "山东省",
    "河南": "河南省",
    "湖北": "湖北省",
    "湖南": "湖南省",
    "广东": "广东省",
    "广西": "广西壮族自治区",
    "海南": "海南省",
    "重庆": "重庆市",
    "四川": "四川省",
    "贵州": "贵州省",
    "云南": "云南省",
    "西藏": "西藏自治区",
    "陕西": "陕西省",
    "甘肃": "甘肃省",
    "青海": "青海省",
    "宁夏": "宁夏回族自治区",
    "新疆": "新疆维吾尔自治区",
    "香港": "香港特别行政区",
    "澳门": "澳门特别行政区",
    "台湾": "台湾省",
}

_MUNICIPALITIES = {"北京市", "天津市", "上海市", "重庆市"}

_cache_lock = threading.Lock()
_mem_cache: dict[str, Any] | None = None
_city_names: set[str] | None = None


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------


def _empty_row(code: str = "") -> dict[str, Any]:
    return {
        "code": code,
        "full_name": "",
        "reg_province": "",
        "reg_city": "",
        "reg_address": "",
        "formatted_address": "",
        "lat": None,
        "lng": None,
        "coord_system": "gcj02",
        "geocode_source": "none",
    }


def _em_code(code: str) -> str:
    """600519 → SH600519（东财 F10 用）。"""
    c = normalize_code(code)
    if not c:
        return ""
    market = detect_market(c)
    prefix = {"sse": "SH", "szse": "SZ", "bse": "BJ"}.get(market, "SH")
    return f"{prefix}{c}"


def _province_short(name: str) -> str:
    return (
        name.replace("省", "")
        .replace("市", "")
        .replace("壮族自治区", "")
        .replace("回族自治区", "")
        .replace("维吾尔自治区", "")
        .replace("自治区", "")
        .replace("特别行政区", "")
    )


def _load_city_names() -> set[str]:
    """城市名表：仅用于从地址里识别市名，不读坐标。"""
    global _city_names
    if _city_names is not None:
        return _city_names
    names: set[str] = set()
    path = _CITY_CENTROIDS_PATH
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}
        if isinstance(raw, dict):
            names = {str(k) for k in raw.keys() if str(k).strip()}
    _city_names = names
    return _city_names


# ---------------------------------------------------------------------------
# 省 / 市解析
# ---------------------------------------------------------------------------


def canonicalize_province(text: str) -> str:
    """任意含省名的文本 → 规范省名（如 广东省）。"""
    raw = safe_str(text)
    if not raw:
        return ""
    if raw in _PROVINCES:
        return raw
    if raw in _PROVINCE_ALIASES:
        return _PROVINCE_ALIASES[raw]
    for canon in sorted(_PROVINCES, key=len, reverse=True):
        short = _province_short(canon)
        if canon in raw or (short and short in raw):
            return canon
    for alias, canon in sorted(_PROVINCE_ALIASES.items(), key=lambda x: -len(x[0])):
        if alias in raw:
            return canon
    return ""


def parse_city(address: str, province: str) -> str:
    """从注册地址解析地级市（直辖市返回「北京」这类短名）。"""
    addr = safe_str(address)
    if not addr:
        return ""
    if province in _MUNICIPALITIES:
        return province.replace("市", "")

    rest = addr.replace("中华人民共和国", "").strip()
    if province:
        for token in (
            province,
            province.replace("省", ""),
            province.replace("市", ""),
            _province_short(province),
        ):
            if token and token in rest:
                rest = rest[rest.find(token) + len(token) :]
                break
        else:
            for alias, canon in _PROVINCE_ALIASES.items():
                if canon == province and alias in rest:
                    rest = rest[rest.find(alias) + len(alias) :]
                    break

    m = re.match(r"([\u4e00-\u9fff]{2,10}(?:市|自治州|州|地区|盟))", rest)
    if m:
        return m.group(1)

    # 「合肥高新技术产业开发区」等：无「市」字
    m2 = re.match(
        r"([\u4e00-\u9fff]{2,6})(?:"
        r"高新技术产业开发区|经济技术开发区|高新技术开发区|"
        r"高新区|经开区|开发区|新区|工业园区|工业园"
        r")",
        rest,
    )
    cities = _load_city_names()
    if m2:
        base = m2.group(1)
        if f"{base}市" in cities:
            return f"{base}市"
        if base in cities:
            return base if base.endswith(("市", "州", "盟")) else f"{base}市"
        return f"{base}市"

    best = ""
    best_len = 0
    for name in cities:
        for v in {name, name.replace("市", ""), name.replace("地区", "")}:
            if len(v) >= 2 and rest.startswith(v) and len(v) > best_len:
                best_len = len(v)
                best = (
                    name
                    if name.endswith(("市", "州", "盟", "地区"))
                    else (f"{name}市" if f"{name}市" in cities else name)
                )
    return best


def _normalize_record(
    code: str,
    *,
    full_name: str = "",
    reg_address: str = "",
    region: str = "",
) -> dict[str, Any]:
    """原文 → 标准 enrich 结构（不含坐标）。"""
    c = normalize_code(code)
    address = safe_str(reg_address)
    province = canonicalize_province(address) or canonicalize_province(region)
    city = parse_city(address, province) if address else ""
    if city and len(city) > 12:
        city = parse_city(address, province) if address else ""
    row = _empty_row(c)
    row.update(
        {
            "full_name": safe_str(full_name),
            "reg_province": province,
            "reg_city": city,
            "reg_address": address,
        }
    )
    return row


# ---------------------------------------------------------------------------
# 缓存
# ---------------------------------------------------------------------------


def _read_disk_cache() -> dict[str, Any]:
    global _mem_cache
    with _cache_lock:
        if _mem_cache is not None:
            return _mem_cache
        ensure_cache_dirs()
        if STOCK_GEO_CACHE.exists():
            try:
                payload = json.loads(STOCK_GEO_CACHE.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    if not isinstance(payload.get("items"), dict):
                        payload["items"] = {}
                    _mem_cache = payload
                    return _mem_cache
            except (OSError, json.JSONDecodeError):
                pass
        _mem_cache = {"version": 1, "items": {}}
        return _mem_cache


def _write_disk_cache() -> None:
    with _cache_lock:
        if _mem_cache is None:
            return
        ensure_cache_dirs()
        STOCK_GEO_CACHE.write_text(
            json.dumps(_mem_cache, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _cache_get(code: str) -> dict[str, Any] | None:
    c = normalize_code(code)
    if not c:
        return None
    row = (_read_disk_cache().get("items") or {}).get(c)
    if not isinstance(row, dict):
        return None
    cached_at = float(row.get("cached_at") or 0)
    if cached_at and time.time() - cached_at > GEO_TTL:
        return None
    # 无全称的旧缓存作废（前端 PlaceSearch 依赖全称）
    if not safe_str(row.get("full_name")):
        return None
    out = _empty_row(c)
    out.update(
        {
            "full_name": safe_str(row.get("full_name")),
            "reg_province": safe_str(row.get("reg_province")),
            "reg_city": safe_str(row.get("reg_city")),
            "reg_address": safe_str(row.get("reg_address")),
            "formatted_address": safe_str(row.get("formatted_address")),
            "lat": row.get("lat"),
            "lng": row.get("lng"),
            "geocode_source": safe_str(row.get("geocode_source")) or "none",
            "poi_name": safe_str(row.get("poi_name")),
            "poi_address": safe_str(row.get("poi_address")),
        }
    )
    return out


def _cache_put(code: str, row: dict[str, Any]) -> None:
    c = normalize_code(code)
    if not c:
        return
    items = _read_disk_cache().setdefault("items", {})
    items[c] = {**row, "cached_at": time.time()}
    _write_disk_cache()


# ---------------------------------------------------------------------------
# 数据源 + 对外 API
# ---------------------------------------------------------------------------


def fetch_registration_raw(code: str) -> dict[str, str]:
    """东财 F10：注册地址 / 区域 / 公司全称。"""
    em = _em_code(code)
    if not em:
        return {"reg_address": "", "region": "", "full_name": ""}
    try:
        resp = http_get(
            _EM_SURVEY_URL,
            params={"code": em},
            headers={
                "Referer": (
                    "https://emweb.securities.eastmoney.com/"
                    f"PC_HSF10/CompanySurvey/Index?type=web&code={em}"
                ),
                "Accept": "application/json, text/plain, */*",
            },
            timeout=20,
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception:  # noqa: BLE001
        return {"reg_address": "", "region": "", "full_name": ""}

    jb = payload.get("jbzl") or {}
    if isinstance(jb, list):
        jb = jb[0] if jb else {}
    if not isinstance(jb, dict):
        return {"reg_address": "", "region": "", "full_name": ""}
    return {
        "reg_address": safe_str(jb.get("zcdz") or jb.get("bgdz")),
        "region": safe_str(jb.get("qy")),
        "full_name": safe_str(jb.get("gsmc")),
    }


def build_geo_record(code: str, *, force: bool = False) -> dict[str, Any]:
    """单只股票：缓存优先，否则拉东财并解析省市区。"""
    c = normalize_code(code)
    if not c:
        return _empty_row()
    if not force:
        cached = _cache_get(c)
        if cached is not None:
            return cached

    raw = fetch_registration_raw(c)
    row = _normalize_record(
        c,
        full_name=raw.get("full_name") or "",
        reg_address=raw.get("reg_address") or "",
        region=raw.get("region") or "",
    )
    _cache_put(c, row)
    return row


def enrich_codes(
    codes: list[str],
    *,
    force: bool = False,
    max_workers: int = 4,
) -> dict[str, dict[str, Any]]:
    """批量 enrich：全称 + 注册省市区（坐标由前端 PlaceSearch 完成）。"""
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in codes:
        c = normalize_code(raw)
        if c and c not in seen:
            seen.add(c)
            cleaned.append(c)

    result: dict[str, dict[str, Any]] = {}
    miss: list[str] = []
    for c in cleaned:
        if not force:
            cached = _cache_get(c)
            if cached is not None and safe_str(cached.get("full_name")):
                result[c] = cached
                continue
        miss.append(c)

    if not miss:
        return result

    workers = max(1, min(max_workers, len(miss)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(build_geo_record, c, force=True): c for c in miss}
        for fut in as_completed(futs):
            c = futs[fut]
            try:
                result[c] = fut.result()
            except Exception:  # noqa: BLE001
                result[c] = _empty_row(c)
    return result
