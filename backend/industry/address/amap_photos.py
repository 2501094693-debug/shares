"""高德 Web 服务：POI 实景图。"""

from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import urlparse

from core.http import get_json

_PHOTO_LIMIT = 6
_AMAP_HOSTS = ("amap.com", "autonavi.com", "amapcdn.com")
_IMG_RE = re.compile(r"\.(jpg|jpeg|png|webp)(\?|$)", re.I)


def _web_key() -> str:
    # JS Key 不能调 Web 服务（USERKEY_PLAT_NOMATCH）；实景图走独立 Web 服务 Key。
    return (os.environ.get("AMAP_WEB_KEY") or "").strip()


def _norm_url(url: str) -> str:
    text = str(url or "").strip()
    if text.startswith("//"):
        text = "https:" + text
    if text.startswith("http://"):
        text = "https://" + text[7:]
    return text


def _is_photo_url(url: str) -> bool:
    if not url.lower().startswith("https://"):
        return False
    host = (urlparse(url).hostname or "").lower()
    if any(host == item or host.endswith("." + item) for item in _AMAP_HOSTS):
        return True
    return bool(_IMG_RE.search(url))


def extract_photo_urls(*sources: Any, limit: int = _PHOTO_LIMIT) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()

    def push(raw: Any) -> None:
        if len(urls) >= limit:
            return
        value: Any = raw
        if isinstance(raw, dict):
            value = (
                raw.get("url")
                or raw.get("picUrl")
                or raw.get("imgUrl")
                or raw.get("src")
                or ""
            )
        url = _norm_url(str(value or ""))
        if not url or url in seen or not _is_photo_url(url):
            return
        seen.add(url)
        urls.append(url)

    def walk(node: Any, depth: int = 0) -> None:
        if len(urls) >= limit or node in (None, "", [], {}, "[]") or depth > 3:
            return
        if isinstance(node, str):
            push(node)
            return
        if isinstance(node, list):
            for item in node:
                walk(item, depth + 1)
            return
        if isinstance(node, dict):
            for key in ("photos", "photo", "pics", "pic"):
                if key in node:
                    walk(node[key], depth + 1)
            push(node)

    for source in sources:
        walk(source)
    return urls[:limit]


def _amap_get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    key = _web_key()
    if not key:
        return {}
    try:
        data = get_json(
            f"https://restapi.amap.com{path}",
            params={**params, "key": key, "output": "json"},
            timeout=8,
        )
    except Exception:  # noqa: BLE001
        return {}
    if not isinstance(data, dict) or str(data.get("status")) != "1":
        return {}
    return data


def _pois(data: dict[str, Any]) -> list[dict[str, Any]]:
    raw = data.get("pois") or []
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def fetch_place_photos(
    *,
    poi_id: str = "",
    lng: float | None = None,
    lat: float | None = None,
    keyword: str = "",
    city: str = "",
) -> list[str]:
    photos: list[str] = []
    poi_id = str(poi_id or "").strip()
    keyword = str(keyword or "").strip()
    city = str(city or "").strip()

    if poi_id:
        data = _amap_get(
            "/v3/place/detail",
            {"id": poi_id, "extensions": "all"},
        )
        photos = extract_photo_urls(*_pois(data), data)
        if len(photos) < 3:
            data_v5 = _amap_get(
                "/v5/place/detail",
                {"id": poi_id, "show_fields": "photos,business"},
            )
            photos = extract_photo_urls(*photos, *_pois(data_v5), data_v5)

    if len(photos) < 3 and lng is not None and lat is not None:
        data = _amap_get(
            "/v3/place/around",
            {
                "location": f"{lng},{lat}",
                "radius": 280,
                "offset": 10,
                "page": 1,
                "extensions": "all",
                "types": "120000|170000|190000|140000|130000",
                "sortrule": "distance",
            },
        )
        photos = extract_photo_urls(*photos, *_pois(data))

    if len(photos) < 3 and keyword:
        params: dict[str, Any] = {
            "keywords": keyword,
            "offset": 8,
            "page": 1,
            "extensions": "all",
        }
        if city:
            params["city"] = city
        data = _amap_get("/v3/place/text", params)
        photos = extract_photo_urls(*photos, *_pois(data))

    return photos[:_PHOTO_LIMIT]
