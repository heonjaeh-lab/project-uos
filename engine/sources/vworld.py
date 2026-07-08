"""V-World 건물통합정보(LT_C_BLDGINFO) 어댑터 — 실측 건물 높이.

OSM 높이 태그(24%)·면적 휴리스틱을 **V-World 실측 height(m)·지상층수**로 대체해
그늘 계산 정확도를 높인다. VWORLD_KEY + 등록 도메인(VWORLD_DOMAIN) 필요.

응답: MultiPolygon(EPSG:4326, [lon,lat]) + properties.height / grnd_flr.
페이징(size≤1000, page=1..total)으로 송파 전역을 받아 캐시한다.
"""

from __future__ import annotations

import json
import os
import time

import requests

from engine.shade.shade import Building
from engine.sources import config

_URL = "https://api.vworld.kr/req/data"
_LAYER = "LT_C_BLDGINFO"
_PAGE_SIZE = 1000
CACHE = "data/cache/songpa_buildings_vworld.json"

# 송파구 대략 bbox (minlon, minlat, maxlon, maxlat)
SONGPA_BBOX = (127.055, 37.470, 127.170, 37.565)
_LEVEL_H = 3.3
_DEFAULT_H = 6.0


def _height(props) -> float:
    for k in ("height",):
        v = props.get(k)
        try:
            h = float(v)
            if h > 0:
                return h
        except (TypeError, ValueError):
            pass
    try:
        fl = float(props.get("grnd_flr"))
        if fl > 0:
            return fl * _LEVEL_H
    except (TypeError, ValueError):
        pass
    return _DEFAULT_H


def _page(bbox, page, key, dom):
    p = {"service": "data", "request": "GetFeature", "data": _LAYER, "key": key,
         "domain": dom, "format": "json", "crs": "EPSG:4326",
         "size": _PAGE_SIZE, "page": page, "geomFilter": "BOX({},{},{},{})".format(*bbox)}
    r = requests.get(_URL, params=p, timeout=40)
    j = r.json()["response"]
    if j.get("status") != "OK":
        return [], 0
    total = int(j.get("page", {}).get("total", 0))
    feats = j.get("result", {}).get("featureCollection", {}).get("features", [])
    return feats, total


def _to_buildings(feats) -> list[Building]:
    out = []
    for f in feats:
        g = f.get("geometry") or {}
        props = f.get("properties", {})
        h = _height(props)
        coords = g.get("coordinates") or []
        polys = coords if g.get("type") == "MultiPolygon" else [coords]
        for poly in polys:
            if not poly:
                continue
            ring = poly[0]  # 외곽 링
            if len(ring) < 3:
                continue
            out.append(Building(footprint=tuple((float(c[0]), float(c[1])) for c in ring),
                                 height_m=h, id=f.get("id")))
    return out


def fetch_songpa_buildings(force: bool = False, bbox=SONGPA_BBOX, max_pages: int = 120) -> list[Building]:
    """송파 전역 V-World 건물 → Building 목록(실측 높이). 페이징+캐시."""
    if not force and os.path.exists(CACHE):
        return _load_cache()
    key, dom = config.get_key("VWORLD_KEY"), config.get_key("VWORLD_DOMAIN")
    if not key:
        raise RuntimeError("VWORLD_KEY 없음")
    feats, total = _page(bbox, 1, key, dom)
    all_feats = list(feats)
    total = min(total, max_pages)
    for pg in range(2, total + 1):
        f, _ = _page(bbox, pg, key, dom)
        if not f:
            break
        all_feats.extend(f)
        time.sleep(0.05)
    buildings = _to_buildings(all_feats)
    _dump_cache(buildings)
    return buildings


def _dump_cache(buildings: list[Building]) -> None:
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump([{"footprint": [list(p) for p in b.footprint],
                    "height_m": b.height_m, "id": b.id} for b in buildings], f)


_MAX_REAL_HEIGHT_M = 555.0  # 국내 최고층(롯데월드타워, 잠실=송파). 이보다 크면 데이터 오류 → 클램프


def _load_cache() -> list[Building]:
    with open(CACHE, encoding="utf-8") as f:
        data = json.load(f)
    out = []
    for b in data:
        h = float(b["height_m"])
        if h > _MAX_REAL_HEIGHT_M:   # 11,700m 등 명백한 오류값 클램프
            h = _MAX_REAL_HEIGHT_M
        out.append(Building(footprint=tuple((float(p[0]), float(p[1])) for p in b["footprint"]),
                            height_m=h, id=b.get("id")))
    return out


__all__ = ["fetch_songpa_buildings", "SONGPA_BBOX"]
