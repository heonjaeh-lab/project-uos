"""서울 열린데이터 어댑터 매핑 검증 — 합성 row로(네트워크 불필요).

라이브 연결은 서비스명이 있어야 하지만, row→DynamicEvent/POI 매핑 로직은 여기서 고정한다.
"""

from __future__ import annotations

from shapely.geometry import Point, shape

from engine.schemas import EventType, POIType
from engine.sources.seoul import construction_events_from_rows, fountains_from_rows


def _poly(ev):
    p = ev.polygon
    return shape(p.model_dump() if hasattr(p, "model_dump") else p)


def test_construction_rows_map_to_dynamic_events():
    rows = [
        {"경도": "127.100", "위도": "37.500", "공사시작일": "2026-07-01", "공사종료일": "2026-07-30"},
        {"LON": "127.110", "LAT": "37.510"},
    ]
    evs = construction_events_from_rows(rows, buffer_m=25.0)
    assert len(evs) == 2
    assert all(e.event_type == EventType.construction for e in evs)
    # 원점이 버퍼 폴리곤 내부에 있어야(M4 교차 판정에 쓰임)
    assert _poly(evs[0]).contains(Point(127.100, 37.500))
    assert evs[0].start is not None and evs[0].end is not None


def test_construction_skips_rows_without_coordinates():
    assert construction_events_from_rows([{"공사명": "무좌표"}]) == []


def test_fountain_rows_map_to_water_fountain_pois():
    pois = fountains_from_rows([{"경도": "127.10", "위도": "37.50", "시설명": "석촌호수 음수대"}])
    assert len(pois) == 1
    assert pois[0].poi_type == POIType.water_fountain
    assert pois[0].name == "석촌호수 음수대"
    assert abs(pois[0].lon - 127.10) < 1e-9


def test_empty_service_returns_nothing():
    from engine.sources import seoul
    # 서비스명 미지정 → 빈 리스트(엔진이 죽지 않음)
    assert seoul.fetch_construction_events(service=None) == []
    assert seoul.fetch_fountains(service=None) == []
