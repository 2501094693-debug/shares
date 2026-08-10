"""上市公司注册地：拉取、解析、坐标与批量 enrich。"""

from __future__ import annotations

import json
import math
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from data.core.paths import GEO_TTL, STOCK_GEO_CACHE, ensure_cache_dirs
from message.disclosure.http_util import detect_market, http_get, normalize_code, safe_str

_FRONTEND_GEO = (
    Path(__file__).resolve().parents[3] / "frontend" / "shared" / "geo"
)
_CITY_CENTROIDS_PATH = _FRONTEND_GEO / "city-centroids.json"
_PROVINCE_CENTROIDS_PATH = _FRONTEND_GEO / "province-centroids.json"

_EM_SURVEY_URL = (
    "https://emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/CompanySurveyAjax"
)
_AMAP_GEOCODE_URL = "https://restapi.amap.com/v3/geocode/geo"

# 规范省名（带后缀）→ 用于聚合与匹配 GeoJSON
PROVINCE_CANONICAL: tuple[str, ...] = (
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

# 短名 / 别名 → 规范省名
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
_city_centroids: dict[str, tuple[float, float]] | None = None
_province_centroids: dict[str, tuple[float, float]] | None = None


def _market_prefix(code: str) -> str:
    market = detect_market(code)
    if market == "sse":
        return "SH"
    if market == "szse":
        return "SZ"
    if market == "bse":
        return "BJ"
    return "SH"


def _em_code(code: str) -> str:
    c = normalize_code(code)
    return f"{_market_prefix(c)}{c}" if c else ""


def _load_json_map(path: Path) -> dict[str, tuple[float, float]]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, tuple[float, float]] = {}
    if isinstance(raw, dict):
        for name, val in raw.items():
            if isinstance(val, (list, tuple)) and len(val) >= 2:
                try:
                    out[str(name)] = (float(val[0]), float(val[1]))
                except (TypeError, ValueError):
                    continue
            elif isinstance(val, dict) and "lat" in val and "lng" in val:
                try:
                    out[str(name)] = (float(val["lat"]), float(val["lng"]))
                except (TypeError, ValueError):
                    continue
    return out


def city_centroids() -> dict[str, tuple[float, float]]:
    global _city_centroids
    if _city_centroids is None:
        _city_centroids = _load_json_map(_CITY_CENTROIDS_PATH)
    return _city_centroids


def province_centroids() -> dict[str, tuple[float, float]]:
    global _province_centroids
    if _province_centroids is None:
        _province_centroids = _load_json_map(_PROVINCE_CENTROIDS_PATH)
    return _province_centroids


def canonicalize_province(text: str) -> str:
    raw = safe_str(text)
    if not raw:
        return ""
    if raw in PROVINCE_CANONICAL:
        return raw
    if raw in _PROVINCE_ALIASES:
        return _PROVINCE_ALIASES[raw]
    # 长名优先匹配
    for canon in sorted(PROVINCE_CANONICAL, key=len, reverse=True):
        short = canon.replace("省", "").replace("市", "")
        short = (
            short.replace("壮族自治区", "")
            .replace("回族自治区", "")
            .replace("维吾尔自治区", "")
            .replace("自治区", "")
            .replace("特别行政区", "")
        )
        if canon in raw or (short and short in raw):
            return canon
    for alias, canon in sorted(_PROVINCE_ALIASES.items(), key=lambda x: -len(x[0])):
        if alias in raw:
            return canon
    return ""


def parse_city(address: str, province: str) -> str:
    """从注册地址中解析地级市名（尽量）。"""
    addr = safe_str(address)
    if not addr:
        return ""
    if province in _MUNICIPALITIES:
        return province.replace("市", "")

    rest = addr.replace("中华人民共和国", "").strip()
    if province:
        tokens = [
            province,
            province.replace("省", ""),
            province.replace("市", ""),
            province.replace("壮族自治区", "")
            .replace("回族自治区", "")
            .replace("维吾尔自治区", "")
            .replace("自治区", "")
            .replace("特别行政区", ""),
        ]
        stripped = False
        for token in tokens:
            if not token:
                continue
            idx = rest.find(token)
            if idx >= 0:
                rest = rest[idx + len(token) :]
                stripped = True
                break
        if not stripped:
            for alias, canon in sorted(
                _PROVINCE_ALIASES.items(), key=lambda x: -len(x[0])
            ):
                if canon != province:
                    continue
                idx = rest.find(alias)
                if idx >= 0:
                    rest = rest[idx + len(alias) :]
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
    if m2:
        base = m2.group(1)
        cities = city_centroids()
        if f"{base}市" in cities:
            return f"{base}市"
        if base in cities:
            return base if base.endswith(("市", "州", "盟")) else f"{base}市"
        return f"{base}市"

    # 用城市中心点表做最长前缀匹配（兼容缺「市」）
    cities = city_centroids()
    best = ""
    best_len = 0
    for name in cities:
        variants = {name, name.replace("市", ""), name.replace("地区", "")}
        for v in variants:
            if len(v) < 2:
                continue
            if rest.startswith(v) and len(v) > best_len:
                best_len = len(v)
                best = name if name.endswith(("市", "州", "盟", "地区")) else (
                    f"{name}市" if f"{name}市" in cities else name
                )
    return best


# --- WGS-84 → GCJ-02（高德 / 国内互联网地图坐标系）---
_PI = 3.1415926535897932384626
_A = 6378245.0
_EE = 0.00669342162296594323


def _out_of_china(lng: float, lat: float) -> bool:
    return not (72.004 <= lng <= 137.8347 and 0.8293 <= lat <= 55.8271)


def _transform_lat(lng: float, lat: float) -> float:
    ret = (
        -100.0
        + 2.0 * lng
        + 3.0 * lat
        + 0.2 * lat * lat
        + 0.1 * lng * lat
        + 0.2 * abs(lng) ** 0.5
    )
    ret += (
        (20.0 * math.sin(6.0 * lng * _PI) + 20.0 * math.sin(2.0 * lng * _PI)) * 2.0 / 3.0
    )
    ret += (20.0 * math.sin(lat * _PI) + 40.0 * math.sin(lat / 3.0 * _PI)) * 2.0 / 3.0
    ret += (
        (160.0 * math.sin(lat / 12.0 * _PI) + 320.0 * math.sin(lat * _PI / 30.0))
        * 2.0
        / 3.0
    )
    return ret


def _transform_lng(lng: float, lat: float) -> float:
    ret = (
        300.0
        + lng
        + 2.0 * lat
        + 0.1 * lng * lng
        + 0.1 * lng * lat
        + 0.1 * abs(lng) ** 0.5
    )
    ret += (
        (20.0 * math.sin(6.0 * lng * _PI) + 20.0 * math.sin(2.0 * lng * _PI)) * 2.0 / 3.0
    )
    ret += (20.0 * math.sin(lng * _PI) + 40.0 * math.sin(lng / 3.0 * _PI)) * 2.0 / 3.0
    ret += (
        (150.0 * math.sin(lng / 12.0 * _PI) + 300.0 * math.sin(lng / 30.0 * _PI))
        * 2.0
        / 3.0
    )
    return ret


def wgs84_to_gcj02(lng: float, lat: float) -> tuple[float, float]:
    """将 WGS-84 经纬度转为 GCJ-02（高德）。"""
    if _out_of_china(lng, lat):
        return lng, lat
    dlat = _transform_lat(lng - 105.0, lat - 35.0)
    dlng = _transform_lng(lng - 105.0, lat - 35.0)
    rad_lat = lat / 180.0 * _PI
    magic = math.sin(rad_lat)
    magic = 1 - _EE * magic * magic
    sqrt_magic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((_A * (1 - _EE)) / (magic * sqrt_magic) * _PI)
    dlng = (dlng * 180.0) / (_A / sqrt_magic * math.cos(rad_lat) * _PI)
    return lng + dlng, lat + dlat


def lookup_coords(province: str, city: str) -> tuple[float | None, float | None]:
    """静态城市/省中心点（WGS-84→GCJ-02），仅作地理编码失败时的回退。"""
    cities = city_centroids()
    provinces = province_centroids()
    candidates: list[str] = []
    if city:
        candidates.extend(
            [
                city,
                city if city.endswith("市") else f"{city}市",
                city.replace("市", ""),
            ]
        )
        if province:
            candidates.append(f"{province}{city}")
    lat: float | None = None
    lng: float | None = None
    for name in candidates:
        if name in cities:
            lat, lng = cities[name]
            break
    if lat is None and province in provinces:
        lat, lng = provinces[province]
    if lat is None or lng is None:
        return None, None
    gcj_lng, gcj_lat = wgs84_to_gcj02(float(lng), float(lat))
    return gcj_lat, gcj_lng


def _amap_web_key() -> str:
    return (
        os.environ.get("AMAP_WEB_KEY")
        or os.environ.get("AMAP_JS_KEY")
        or os.environ.get("AMAP_KEY")
        or ""
    ).strip()


def geocode_amap(
    address: str,
    *,
    city: str = "",
) -> dict[str, Any] | None:
    """高德地理编码（返回 GCJ-02）。需要 Web 服务 Key（或已开通地理编码的 Key）。"""
    addr = safe_str(address)
    key = _amap_web_key()
    if not addr or not key:
        return None
    params: dict[str, str] = {
        "key": key,
        "address": addr,
        "output": "JSON",
    }
    city_hint = safe_str(city)
    if city_hint:
        params["city"] = city_hint
    try:
        resp = http_get(_AMAP_GEOCODE_URL, params=params, timeout=15)
        resp.raise_for_status()
        payload = resp.json()
    except Exception:  # noqa: BLE001
        return None
    if str(payload.get("status")) != "1":
        return None
    geocodes = payload.get("geocodes") or []
    if not geocodes:
        return None
    row = geocodes[0] if isinstance(geocodes[0], dict) else {}
    location = safe_str(row.get("location"))
    if "," not in location:
        return None
    try:
        lng_s, lat_s = location.split(",", 1)
        lng, lat = float(lng_s), float(lat_s)
    except ValueError:
        return None
    return {
        "lat": lat,
        "lng": lng,
        "formatted_address": safe_str(row.get("formatted_address")),
        "province": safe_str(row.get("province")),
        "city": safe_str(row.get("city"))
        if not isinstance(row.get("city"), list)
        else safe_str((row.get("city") or [""])[0] if row.get("city") else ""),
        "district": safe_str(row.get("district")),
        "geocode_source": "amap",
        "coord_system": "gcj02",
    }


def resolve_coords(
    *,
    address: str,
    province: str,
    city: str,
) -> tuple[float | None, float | None, str, str]:
    """优先高德地理编码；失败再回退城市中心点。返回 lat,lng,source,formatted。"""
    addr = safe_str(address)
    # 地址过短时拼省市区，提高命中率
    query = addr
    if not query:
        query = f"{safe_str(province)}{safe_str(city)}"
    elif province and province not in query:
        query = f"{province}{query}"

    hit = geocode_amap(query, city=city or province)
    if hit and hit.get("lat") is not None and hit.get("lng") is not None:
        return (
            float(hit["lat"]),
            float(hit["lng"]),
            "amap",
            safe_str(hit.get("formatted_address")),
        )

    lat2, lng2 = lookup_coords(province, city)
    if lat2 is not None and lng2 is not None:
        return lat2, lng2, "centroid", ""
    return None, None, "", ""


def normalize_geo_fields(
    *,
    code: str,
    reg_address: str = "",
    region: str = "",
    reg_province: str = "",
    reg_city: str = "",
    full_name: str = "",
    lat: Any = None,
    lng: Any = None,
    coord_system: str = "",
    geocode_source: str = "",
    formatted_address: str = "",
    do_geocode: bool = True,
) -> dict[str, Any]:
    """由原文规范出省/市/全称；坐标可选（前端优先用高德 PlaceSearch）。"""
    c = normalize_code(code)
    address = safe_str(reg_address)
    region = safe_str(region)
    full = safe_str(full_name)
    province = (
        safe_str(reg_province)
        or canonicalize_province(address)
        or canonicalize_province(region)
    )
    city = parse_city(address, province) if address else safe_str(reg_city)
    if city and len(city) > 12:
        city = parse_city(address, province) if address else ""

    src = safe_str(geocode_source).lower()
    fmt = safe_str(formatted_address)
    lat2: float | None = None
    lng2: float | None = None

    # 已是高德结果可复用
    if (
        src in {"amap", "amap_place"}
        and lat is not None
        and lng is not None
        and safe_str(coord_system).lower() in {"", "gcj02"}
    ):
        try:
            lat2, lng2 = float(lat), float(lng)
        except (TypeError, ValueError):
            lat2, lng2 = None, None

    # 后端地理编码改为可选回退；主路径由前端 PlaceSearch(公司全称) 标点
    if do_geocode and lat2 is None:
        g_lat, g_lng, g_src, g_fmt = resolve_coords(
            address=address, province=province, city=city
        )
        if g_lat is not None:
            lat2, lng2 = g_lat, g_lng
            src = g_src
            if g_fmt:
                fmt = g_fmt

    return {
        "code": c,
        "full_name": full,
        "reg_province": province,
        "reg_city": city,
        "reg_address": address,
        "formatted_address": fmt,
        "lat": lat2,
        "lng": lng2,
        "coord_system": "gcj02",
        "geocode_source": src or "none",
    }


def _read_disk_cache() -> dict[str, Any]:
    global _mem_cache
    with _cache_lock:
        if _mem_cache is not None:
            return _mem_cache
        ensure_cache_dirs()
        if not STOCK_GEO_CACHE.exists():
            _mem_cache = {"version": 1, "items": {}}
            return _mem_cache
        try:
            payload = json.loads(STOCK_GEO_CACHE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            _mem_cache = {"version": 1, "items": {}}
            return _mem_cache
        if not isinstance(payload, dict):
            _mem_cache = {"version": 1, "items": {}}
            return _mem_cache
        items = payload.get("items")
        if not isinstance(items, dict):
            payload["items"] = {}
        _mem_cache = payload
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
    payload = _read_disk_cache()
    row = (payload.get("items") or {}).get(c)
    if not isinstance(row, dict):
        return None
    cached_at = float(row.get("cached_at") or 0)
    if cached_at and time.time() - cached_at > GEO_TTL:
        return None
    # 无公司全称的旧缓存作废，强制重拉 gsmc
    if not safe_str(row.get("full_name")):
        return None
    return {
        "code": c,
        "full_name": safe_str(row.get("full_name")),
        "reg_province": safe_str(row.get("reg_province")),
        "reg_city": safe_str(row.get("reg_city")),
        "reg_address": safe_str(row.get("reg_address")),
        "formatted_address": safe_str(row.get("formatted_address")),
        "lat": row.get("lat"),
        "lng": row.get("lng"),
        "coord_system": "gcj02",
        "geocode_source": safe_str(row.get("geocode_source")) or "none",
        "poi_name": safe_str(row.get("poi_name")),
        "poi_address": safe_str(row.get("poi_address")),
    }


def _cache_put(code: str, row: dict[str, Any]) -> None:
    c = normalize_code(code)
    if not c:
        return
    payload = _read_disk_cache()
    items = payload.setdefault("items", {})
    items[c] = {**row, "cached_at": time.time()}
    _write_disk_cache()


def fetch_registration_raw(code: str) -> dict[str, str]:
    """从东财 F10 拉取注册地址 / 区域 / 公司全称。"""
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
    c = normalize_code(code)
    empty = {
        "code": c,
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
    if not c:
        return empty
    if not force:
        cached = _cache_get(c)
        if cached is not None:
            return cached

    raw = fetch_registration_raw(c)
    # 主路径：拉全称+省市区；坐标留给前端 PlaceSearch（公司全称）
    row = normalize_geo_fields(
        code=c,
        reg_address=raw.get("reg_address") or "",
        region=raw.get("region") or "",
        full_name=raw.get("full_name") or "",
        do_geocode=False,
    )
    _cache_put(c, row)
    return row


def enrich_codes(
    codes: list[str],
    *,
    force: bool = False,
    max_workers: int = 4,
) -> dict[str, dict[str, Any]]:
    """批量 enrich：公司全称 + 注册省市区（坐标由前端高德 PlaceSearch 标注）。"""
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in codes:
        c = normalize_code(raw)
        if not c or c in seen:
            continue
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

    if miss:
        workers = max(1, min(max_workers, len(miss)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {
                pool.submit(build_geo_record, c, force=True): c for c in miss
            }
            for fut in as_completed(futs):
                c = futs[fut]
                try:
                    result[c] = fut.result()
                except Exception:  # noqa: BLE001
                    result[c] = {
                        "code": c,
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

    return result
