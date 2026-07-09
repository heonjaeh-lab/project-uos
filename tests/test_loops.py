"""GPS 무목적지(동네 순환) 모드 다중 변형 — `recommend_loops` 검증.

`recommend_routes`(목적지 있는 다중 경로 추천)의 순환판. `neighborhood_loop`을
서로 다른 `CostParams.shade_bonus`·목표 거리로 여러 번 돌려 그늘 많은 순환/짧은
순환처럼 서로 다른 루프 후보를 모으고, node_path가 같은 중복은 제거하며, 최소
1개(동네 순환 폴백)는 보장하는지 **실네트워크 없이**(합성 그래프) 검증한다.

실행: `.venv/bin/python -m pytest tests/test_loops.py -q`
"""

from __future__ import annotations

import math

import networkx as nx

from engine.routing import recommend_loops, route_payload
from engine.schemas import RiskLevel

START = 0
TARGET_M = 1200.0

# neighborhood_loop의 turnaround 후보 필터는 출발점 기준 haversine 거리가
# [0.15, 0.35] * target_m 안에 있는 노드만 후보로 본다. recommend_loops는
# target_m(1200) 그대로인 변형과 target_m*0.75(=900)인 변형을 함께 시도하므로,
# 두 밴드([180,420] / [135,315])에 모두 걸리는 값(250m)을 골라 turnaround
# 노드를 배치한다(router.py `neighborhood_loop` 후보 필터 참조).
_TURNAROUND_DIST_M = 250.0
_LAT_DEG_PER_M = 1.0 / 111320.0


def _offset_node(lat0: float, lon0: float, *, north: bool, dist_m: float = _TURNAROUND_DIST_M):
    """출발점(lat0, lon0)에서 북쪽 또는 동쪽으로 dist_m 떨어진 좌표(근사)."""
    if north:
        return lat0 + dist_m * _LAT_DEG_PER_M, lon0
    lon_deg_per_m = 1.0 / (111320.0 * math.cos(math.radians(lat0)))
    return lat0, lon0 + dist_m * lon_deg_per_m


def _two_arm_star() -> nx.MultiDiGraph:
    """출발(0)에서 그늘 아치(1, 왕복 1200m·그늘 100%)와 짧은 아치(2, 왕복 900m·
    그늘 0%)로 뻗은 별 모양 그래프.

    두 turnaround 모두 haversine 250m로 둬 두 target 스케일(1200/900)의 후보
    밴드에 함께 걸리게 했다. 실제 왕복 거리(엣지 `length`)는 좌표와 독립적으로
    통제한다(다른 toy 그래프와 같은 관례 — tests/test_routing.py 참조).
    """
    lat0, lon0 = 37.500, 127.100
    lat1, lon1 = _offset_node(lat0, lon0, north=True)
    lat2, lon2 = _offset_node(lat0, lon0, north=False)

    G = nx.MultiDiGraph()
    G.add_node(START, x=lon0, y=lat0)
    G.add_node(1, x=lon1, y=lat1)  # 그늘 아치 turnaround
    G.add_node(2, x=lon2, y=lat2)  # 짧은 아치 turnaround

    def _add(u, v, length, shade):
        for a, b in ((u, v), (v, u)):
            G.add_edge(a, b, length=length, shade_ratio=shade, hazards=[],
                       risk_level=RiskLevel.green.value, traffic=0.0)

    _add(START, 1, length=600.0, shade=1.0)  # 왕복 1200m, 그늘 100%
    _add(START, 2, length=450.0, shade=0.0)  # 왕복 900m, 그늘 0%
    return G


def _single_arm_star() -> nx.MultiDiGraph:
    """turnaround 후보가 하나뿐인 그래프 — 모든 변형이 같은 루프로 collapse."""
    lat0, lon0 = 37.500, 127.100
    lat1, lon1 = _offset_node(lat0, lon0, north=True)

    G = nx.MultiDiGraph()
    G.add_node(START, x=lon0, y=lat0)
    G.add_node(1, x=lon1, y=lat1)

    for a, b in ((START, 1), (1, START)):
        G.add_edge(a, b, length=600.0, shade_ratio=0.6, hazards=[],
                   risk_level=RiskLevel.green.value, traffic=0.0)
    return G


# ---------------------------------------------------------------------------
# (a)(b) 서로 다른 변형 여러 개 + route_payload 소비 가능
# ---------------------------------------------------------------------------


def test_recommend_loops_returns_distinct_variants_consumable_by_payload():
    G = _two_arm_star()
    opts = recommend_loops(G, START, TARGET_M, [])
    assert 1 <= len(opts) <= 3
    assert len(opts) == 2, "그늘 아치/짧은 아치 — 서로 다른 두 변형이 나와야 한다"

    labels = [o["label"] for o in opts]
    assert "그늘 최대" in labels and "짧은 순환" in labels

    shades = [o["route"].avg_shade_ratio for o in opts]
    assert shades == sorted(shades, reverse=True), "그늘 많은 순 정렬"

    for o in opts:
        r = o["route"]
        assert r.reason is None
        assert r.node_path[0] == r.node_path[-1] == START  # 출발=도착(순환)

    # route_payload가 그대로 소비 가능(예외 없이 dict 생성 + 필수 키 존재).
    for o in opts:
        payload = route_payload(G, o["route"], o["label"])
        assert payload["label"] == o["label"]
        assert payload["distance_m"] > 0
        assert "segs" in payload and "pois" in payload


# ---------------------------------------------------------------------------
# (c) 결정론 — 같은 입력 반복 시 동일 라벨·거리
# ---------------------------------------------------------------------------


def test_recommend_loops_is_deterministic():
    G = _two_arm_star()
    opts1 = recommend_loops(G, START, TARGET_M, [])
    opts2 = recommend_loops(G, START, TARGET_M, [])
    assert [o["label"] for o in opts1] == [o["label"] for o in opts2]
    assert ([o["route"].model_dump() for o in opts1]
            == [o["route"].model_dump() for o in opts2])


# ---------------------------------------------------------------------------
# (d) 후보 collapse → 최소 1개 '동네 순환' 폴백
# ---------------------------------------------------------------------------


def test_recommend_loops_collapses_to_single_fallback_label():
    G = _single_arm_star()
    opts = recommend_loops(G, START, TARGET_M, [])
    assert len(opts) == 1
    assert opts[0]["label"] == "동네 순환"
    r = opts[0]["route"]
    assert r.reason is None
    assert r.node_path[0] == r.node_path[-1] == START


# ---------------------------------------------------------------------------
# 부가: max_routes 상한 + 후보 전무 시 빈 리스트
# ---------------------------------------------------------------------------


def test_recommend_loops_respects_max_routes_cap():
    G = _two_arm_star()
    opts = recommend_loops(G, START, TARGET_M, [], max_routes=1)
    assert len(opts) == 1
    assert opts[0]["label"] == "그늘 최대"  # 상한이 걸려도 그늘 많은 쪽이 남는다.


def test_recommend_loops_no_candidates_returns_empty_list():
    """turnaround 후보가 전혀 없는(밴드에 노드가 없는) 그래프 → 빈 리스트."""
    G = nx.MultiDiGraph()
    G.add_node(START, x=127.100, y=37.500)
    opts = recommend_loops(G, START, TARGET_M, [])
    assert opts == []
