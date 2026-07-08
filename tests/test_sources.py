"""OSM 실데이터 어댑터 검증(engine.sources.osm).

캐시(data/cache/songpa_*.json)가 있으면 매핑 정합을 검증하고, 없으면 skip한다
(네트워크/fetch 의존이므로 CI에서 캐시 없이도 안전).

실행: PYTHONPATH=. .venv/bin/python -m pytest tests/test_sources.py -q
"""

from __future__ import annotations

import os

import pytest

from engine.schemas import POI, POIType
from engine.shade.shade import Building, Tree

BUILDINGS_CACHE = "data/cache/songpa_buildings.json"
POIS_CACHE = "data/cache/songpa_pois.json"


@pytest.mark.skipif(not os.path.exists(BUILDINGS_CACHE), reason="건물 캐시 없음(fetch 필요)")
def test_buildings_mapped_with_valid_heights():
    from engine.sources import osm
    buildings = osm.fetch_buildings()
    assert len(buildings) > 1000, "송파구 건물이 충분히 로드되어야"
    for b in buildings[:500]:
        assert isinstance(b, Building)
        assert b.height_m > 0, "높이는 양수(태그 없으면 기본값)"
        assert len(b.footprint) >= 3, "footprint는 최소 3점 링"
        lon, lat = b.footprint[0]
        assert 126.9 < lon < 127.3 and 37.4 < lat < 37.6, "송파구 경위도 범위"


@pytest.mark.skipif(not os.path.exists(POIS_CACHE), reason="POI 캐시 없음(fetch 필요)")
def test_pois_mapped_to_schema_types():
    from engine.sources import osm
    pois = osm.fetch_pois()
    assert len(pois) > 50
    for p in pois:
        assert isinstance(p, POI)
        assert isinstance(p.poi_type, POIType)
        assert 37.4 < p.lat < 37.6 and 126.9 < p.lon < 127.3
    # 동물병원이 실제로 매핑되었는가(기획서 핵심 안전 지점).
    assert any(p.poi_type == POIType.animal_hospital for p in pois)


@pytest.mark.skipif(not os.path.exists(BUILDINGS_CACHE), reason="건물 캐시 없음")
def test_buildings_cache_is_deterministic():
    from engine.sources import osm
    a = osm.fetch_buildings()
    b = osm.fetch_buildings()
    assert len(a) == len(b)
    assert a[0].footprint == b[0].footprint and a[0].height_m == b[0].height_m
