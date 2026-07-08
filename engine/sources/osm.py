"""OSM 실데이터 어댑터 (키 불필요) — 송파구 건물·POI·가로수.

- 건물: footprint + 높이(m). 높이는 `height` 태그 → `building:levels`×층고 → 기본값 순.
- POI: 동물병원·화장실·급수대·공원·펫샵 → engine.schemas.POI.
- 가로수: natural=tree 포인트 → engine.shade.Tree (OSM은 희박 — 서울 열린데이터광장이 보강).

느린 Overpass 호출 결과는 `data/cache/`에 JSON으로 캐시해 재사용한다(재다운로드 금지).
좌표는 WGS84. footprint/POI 좌표는 (lon, lat) 순서(GeoJSON 계약).
"""

from __future__ import annotations

import json
import math
import os
import re

from engine.schemas import POI, POIType
from engine.shade.shade import Building, Tree

PLACE = "Songpa-gu, Seoul, South Korea"
CACHE_DIR = "data/cache"

_BUILDINGS_CACHE = f"{CACHE_DIR}/songpa_buildings.json"
_TREES_CACHE = f"{CACHE_DIR}/songpa_trees.json"
_POIS_CACHE = f"{CACHE_DIR}/songpa_pois.json"

# 매핑: OSM 태그 → POIType
_POI_TAGS = {
    "amenity": ["toilets", "drinking_water", "veterinary"],
    "leisure": ["park", "dog_park"],
    "shop": ["pet"],
}
_POI_MAP = {
    ("amenity", "toilets"): POIType.toilet,
    ("amenity", "drinking_water"): POIType.water_fountain,
    ("amenity", "veterinary"): POIType.animal_hospital,
    ("leisure", "park"): POIType.park,
    ("leisure", "dog_park"): POIType.park,
    ("shop", "pet"): POIType.pet_shop,
}

_DEFAULT_HEIGHT_M = 4.0   # 저층 주택/부속(면적도 작을 때)
_LEVEL_HEIGHT_M = 3.3     # building:levels 1개당 층고


def _num(value) -> float | None:
    """'12', '12 m', '12.5' 같은 태그 문자열에서 첫 숫자를 뽑는다."""
    if value is None:
        return None
    try:
        import pandas as pd
        if pd.isna(value):
            return None
    except Exception:
        pass
    m = re.search(r"[-+]?\d*\.?\d+", str(value))
    return float(m.group()) if m else None


def _height_from_area(area_m2: float) -> float:
    """높이·층수 태그가 모두 없을 때 footprint 면적으로 높이 추정.

    송파구는 아파트 밀집 지역이라, 큰 footprint는 대개 중·고층이다. 평면적 4m
    기본값은 그림자를 과소평가하므로 면적 구간별로 잠정 높이를 준다.
    ⚠️ 어디까지나 휴리스틱 — V-World 실측 건물높이로 교체할 것.
    """
    if area_m2 >= 700:
        return 45.0   # 대형 동(아파트)
    if area_m2 >= 350:
        return 24.0   # 중형 건물
    if area_m2 >= 150:
        return 12.0   # 준중형
    return _DEFAULT_HEIGHT_M


def _building_height(height, levels, area_m2: float = 0.0) -> float:
    h = _num(height)
    if h and h > 0:
        return h
    lv = _num(levels)
    if lv and lv > 0:
        return lv * _LEVEL_HEIGHT_M
    return _height_from_area(area_m2)


def _approx_area_m2(poly) -> float:
    """경위도 폴리곤의 대략 면적(m²) — 높이 구간 판정용 근사."""
    lat = poly.centroid.y
    return poly.area * 111_000.0 * (111_000.0 * math.cos(math.radians(lat)))


# ---------------------------------------------------------------------------
# fetch + cache (Overpass 호출은 여기서만)
# ---------------------------------------------------------------------------


def _features(tags):
    import osmnx as ox
    ox.settings.use_cache = True
    ox.settings.cache_folder = CACHE_DIR
    return ox.features_from_place(PLACE, tags=tags)


def fetch_buildings(force: bool = False) -> list[Building]:
    """송파구 건물 → Building 목록(footprint + 높이 m). 캐시 우선."""
    if not force and os.path.exists(_BUILDINGS_CACHE):
        return _load_buildings_cache()
    from shapely.geometry import MultiPolygon, Polygon

    gdf = _features({"building": True})
    out: list[Building] = []
    for idx, row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        polys = []
        if isinstance(geom, Polygon):
            polys = [geom]
        elif isinstance(geom, MultiPolygon):
            polys = list(geom.geoms)
        else:
            continue
        for k, poly in enumerate(polys):
            height = _building_height(row.get("height"), row.get("building:levels"),
                                      area_m2=_approx_area_m2(poly))
            ring = [(float(x), float(y)) for x, y in poly.exterior.coords]
            osmid = idx[1] if isinstance(idx, tuple) else idx
            out.append(Building(footprint=tuple(ring), height_m=height, id=f"{osmid}_{k}"))
    _dump_buildings_cache(out)
    return out


def fetch_trees(force: bool = False, canopy_radius_m: float = 3.0) -> list[Tree]:
    """송파구 가로수(natural=tree) → Tree 목록. OSM은 희박(수십 개)."""
    if not force and os.path.exists(_TREES_CACHE):
        with open(_TREES_CACHE, encoding="utf-8") as f:
            return [Tree(**t) for t in json.load(f)]
    gdf = _features({"natural": "tree"})
    out: list[Tree] = []
    for idx, row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty or geom.geom_type != "Point":
            continue
        osmid = idx[1] if isinstance(idx, tuple) else idx
        out.append(Tree(lat=float(geom.y), lon=float(geom.x),
                        canopy_radius_m=canopy_radius_m, id=str(osmid)))
    with open(_TREES_CACHE, "w", encoding="utf-8") as f:
        json.dump([{"lat": t.lat, "lon": t.lon,
                    "canopy_radius_m": t.canopy_radius_m, "id": t.id} for t in out],
                  f, ensure_ascii=False)
    return out


def fetch_pois(force: bool = False) -> list[POI]:
    """송파구 POI(동물병원·화장실·급수대·공원·펫샵) → POI 목록. 폴리곤은 중심점."""
    if not force and os.path.exists(_POIS_CACHE):
        with open(_POIS_CACHE, encoding="utf-8") as f:
            return [POI.model_validate(p) for p in json.load(f)]
    gdf = _features(_POI_TAGS)
    out: list[POI] = []
    for idx, row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        poi_type = None
        for key in ("amenity", "leisure", "shop"):
            val = row.get(key)
            if val is not None and (key, val) in _POI_MAP:
                poi_type = _POI_MAP[(key, val)]
                break
        if poi_type is None:
            continue
        pt = geom if geom.geom_type == "Point" else geom.centroid
        name = row.get("name")
        try:
            import pandas as pd
            if name is None or pd.isna(name):
                name = poi_type.value
        except Exception:
            name = name or poi_type.value
        out.append(POI(poi_type=poi_type, lat=float(pt.y), lon=float(pt.x),
                       name=str(name), open_now=None))
    with open(_POIS_CACHE, "w", encoding="utf-8") as f:
        json.dump([p.model_dump() for p in out], f, ensure_ascii=False)
    return out


# ---------------------------------------------------------------------------
# 건물 캐시 직렬화 (footprint 링 보존)
# ---------------------------------------------------------------------------


def _dump_buildings_cache(buildings: list[Building]) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    data = [{"footprint": [list(pt) for pt in b.footprint],
             "height_m": b.height_m, "id": b.id} for b in buildings]
    with open(_BUILDINGS_CACHE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def _load_buildings_cache() -> list[Building]:
    with open(_BUILDINGS_CACHE, encoding="utf-8") as f:
        data = json.load(f)
    return [Building(footprint=tuple((float(p[0]), float(p[1])) for p in b["footprint"]),
                     height_m=float(b["height_m"]), id=b.get("id")) for b in data]


__all__ = ["fetch_buildings", "fetch_trees", "fetch_pois", "PLACE"]
