"""engine.routing.payload — 프론트 map_data 스키마 직렬화(순수, 네트워크 없음)."""
from __future__ import annotations

import networkx as nx
import pytest

from engine.routing.payload import edge_polyline, route_payload, routes_bbox
from engine.schemas import RiskLevel
from engine.schemas.poi import POI, POIType
from engine.schemas.route import RouteResult


def _toy_graph() -> nx.MultiDiGraph:
    # A(1)→C(3)→B(2). geometry 없음 → 노드 좌표로 폴백. shade_ratio·cost 부여.
    G = nx.MultiDiGraph()
    G.add_node(1, x=127.100, y=37.500)
    G.add_node(2, x=127.102, y=37.500)
    G.add_node(3, x=127.101, y=37.501)
    for a, b, sh in ((1, 3, 0.8), (3, 2, 0.4)):
        for u, v in ((a, b), (b, a)):
            G.add_edge(u, v, length=70.0, shade_ratio=sh, cost=70.0)
    return G


def test_edge_polyline_falls_back_to_node_coords():
    G = _toy_graph()
    line, shade = edge_polyline(G, 1, 3)
    assert line == [[127.1, 37.5], [127.101, 37.501]]   # [lon,lat]
    assert shade == 0.8


def test_route_payload_shape():
    G = _toy_graph()
    r = RouteResult(
        node_path=[1, 3, 2], distance_m=140.0, est_time_min=1.9,
        avg_shade_ratio=0.6, max_risk_level=RiskLevel.green,
        pois_on_route=[POI(poi_type=POIType.water_fountain, lat=37.5005,
                           lon=127.1005, name="급수대")],
    )
    p = route_payload(G, r, "동네 순환")
    assert p["label"] == "동네 순환"
    assert p["shade"] == 0.6 and p["distance_m"] == 140 and p["max_risk"] == "green"
    assert len(p["segs"]) == 2
    assert p["segs"][0]["line"] == [[127.1, 37.5], [127.101, 37.501]]
    assert p["pois"][0] == {"lon": 127.1005, "lat": 37.5005,
                            "type": "water_fountain", "name": "급수대"}


def test_route_payload_clear_shade_eff_equals_geometric():
    # clearness 기본 1.0(맑음) → shade_eff == shade, seg.shade_eff == seg.shade (회귀 없음)
    G = _toy_graph()
    r = RouteResult(node_path=[1, 3, 2], avg_shade_ratio=0.6,
                    max_risk_level=RiskLevel.green)
    p = route_payload(G, r, "x")
    assert p["shade_eff"] == p["shade"]
    for s in p["segs"]:
        assert s["shade_eff"] == pytest.approx(s["shade"])


def test_route_payload_overcast_raises_effective_and_preserves_raw():
    # 흐림(clearness=0.1) → 실질 그늘↑, 기하 raw 는 보존
    G = _toy_graph()
    r = RouteResult(node_path=[1, 3, 2], avg_shade_ratio=0.6,
                    max_risk_level=RiskLevel.green)
    p = route_payload(G, r, "x", clearness=0.1)
    assert p["shade"] == 0.6                       # raw 보존
    assert p["shade_eff"] == pytest.approx(0.96)   # 1-(1-0.6)*0.1
    assert p["shade_eff"] > p["shade"]
    for s in p["segs"]:
        assert s["shade_eff"] >= s["shade"]        # 세그도 실질 그늘 >= 기하


def test_routes_bbox_covers_all_points_with_pad():
    G = _toy_graph()
    r = RouteResult(node_path=[1, 3, 2], max_risk_level=RiskLevel.green)
    routes = [route_payload(G, r, "x")]
    bb = routes_bbox(routes, pad=0.001)
    assert bb == pytest.approx([127.099, 37.499, 127.103, 37.502])   # min-pad .. max+pad (float)


def test_routes_bbox_empty_uses_center():
    bb = routes_bbox([], center=(37.5, 127.0))
    assert bb == pytest.approx([126.99, 37.49, 127.01, 37.51])
