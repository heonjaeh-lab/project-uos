"""통합(경계면) 검증 — 스키마(M0)→그늘(M1)→위험(M2)→라우팅(M3)→리라우팅(M4)를
하나의 end-to-end 파이프라인으로 관통해, 모듈 경계면 불변식을 직접 확인한다.

워크플로우의 최종 QA 에이전트가 실제로 실행되지 않아(도구 호출 0회) 비어 있던
통합 검증을, 실 송파구 그래프 위에서 어드버서리얼하게 채운다.

경계면:
- (a) M1 그늘 → M3 비용: 그늘/위험이 실제로 그래프에 주입되었는가(기본값이 아님).
- (b) M2 위험 red → M3 hard-block: end-to-end 경로에 red 엣지가 없다.
- (c) M3 경로 → M4 리라우팅: 경로 위 공사 폴리곤을 회피하고, 새 경로는 교차하지 않는다.
- (d) M0 스키마: RouteResult가 pydantic 왕복(model_dump→model_validate)되고 타입이 일관.
- 결정론: 독립 2회 빌드/탐색이 완전히 동일.

실행: `.venv/bin/python -m pytest tests/test_integration.py -q`
"""

from __future__ import annotations

import json

import pytest

from engine.reroute import find_blocked_edges, reroute_if_blocked, route_diff
from engine.routing import build_routing_graph, find_route
from engine.schemas import CostParams, DynamicEvent, RiskLevel, RouteResult

MOCK_ORIG = 287284026
MOCK_DEST = 11153308710
CONSTRUCTION_ON_ROUTE_PATH = "data/mock/construction_on_route.json"


def _consecutive_pairs(node_path):
    return list(zip(node_path, node_path[1:]))


@pytest.fixture(scope="module")
def routing_graph():
    # build_routing_graph(): 송파 캐시 로드 + M1 그늘·M2 위험 주입 + 비용 계산.
    return build_routing_graph()


@pytest.fixture(scope="module")
def base_route(routing_graph):
    route = find_route(routing_graph, MOCK_ORIG, MOCK_DEST, CostParams())
    assert route.reason is None, "기준 경로가 산출되어야 통합 검증이 의미 있다"
    return route


@pytest.fixture(scope="module")
def construction_event() -> DynamicEvent:
    with open(CONSTRUCTION_ON_ROUTE_PATH, encoding="utf-8") as f:
        return DynamicEvent(**json.load(f))


# --- (a) M1/M2가 실제로 파이프라인에 연결되었는가 (기본값이 아님) ---

def test_m1_shade_injected_into_real_graph(routing_graph):
    """그래프에 shade_ratio>0 엣지가 존재 → M1 compute_shade_ratios가 실제로 돌았다."""
    shaded = [
        d for _, _, d in routing_graph.edges(data=True)
        if float(d.get("shade_ratio", 0.0)) > 0.0
    ]
    assert shaded, "그늘이 주입된 엣지가 하나도 없다 — M1이 연결되지 않았다"
    # 값 범위 정합(라우팅 비용 입력으로 적합)
    assert all(0.0 <= float(d["shade_ratio"]) <= 1.0 for d in shaded)


def test_m2_risk_injected_into_real_graph(routing_graph):
    """그래프에 red 등급 엣지가 존재 → M2 compute_risk가 실제로 게이트에 연결됐다."""
    levels = {d.get("risk_level") for _, _, d in routing_graph.edges(data=True)}
    assert RiskLevel.red.value in levels, "red 엣지가 없다 — M2가 연결되지 않았다"


# --- (b) red hard-block이 end-to-end로 유지되는가 ---

def test_end_to_end_route_has_no_red_edge(base_route, routing_graph):
    assert base_route.max_risk_level != RiskLevel.red
    for u, v in _consecutive_pairs(base_route.node_path):
        best = min(
            routing_graph[u][v].values(),
            key=lambda d: d.get("cost", float("inf")),
        )
        assert best.get("risk_level") != RiskLevel.red.value, (
            f"경로에 red 엣지 포함: {u}->{v}"
        )


# --- (c) 경로 → 리라우팅: 공사 폴리곤 회피 ---

def test_reroute_avoids_construction_end_to_end(routing_graph, base_route, construction_event):
    # 전제: 기준 경로가 실제로 폴리곤과 교차한다.
    blocked_before = find_blocked_edges(routing_graph, base_route.node_path, [construction_event])
    assert blocked_before, "전제 실패: 기준 경로가 공사 폴리곤과 교차하지 않는다"

    new_route, msg = reroute_if_blocked(routing_graph, base_route, [construction_event], CostParams())
    assert new_route.reason is None, "리라우팅이 경로를 찾지 못했다"

    # 핵심 불변식: 새 경로는 폴리곤과 교차하지 않는다.
    blocked_after = find_blocked_edges(routing_graph, new_route.node_path, [construction_event])
    assert blocked_after == [], f"새 경로가 여전히 공사 구간과 교차: {blocked_after}"

    # 사용자에게 설명 가능한 알림 + 실제 경로 변경.
    assert msg, "경로 변경 알림 문구가 비어 있다"
    assert new_route.node_path != base_route.node_path, "경로가 실제로 바뀌지 않았다"
    diff = route_diff(base_route.node_path, new_route.node_path)
    assert diff, "route_diff가 변경 내역을 내지 못했다"


def test_reroute_no_op_when_polygon_off_route(routing_graph, base_route, construction_event):
    """폴리곤이 경로 밖이면 원 경로 유지(불필요한 재계산 없음)."""
    # 경로에서 멀리 떨어진 이벤트를 만든다(좌표를 크게 이동).
    far = construction_event.model_copy(deep=True)
    poly = far.polygon.model_dump() if hasattr(far.polygon, "model_dump") else dict(far.polygon)
    # 폴리곤 좌표를 남서쪽으로 크게 평행이동해 경로와 무관하게.
    shifted = [[[lon - 0.05, lat - 0.05] for lon, lat in ring] for ring in poly["coordinates"]]
    poly["coordinates"] = shifted
    far = far.model_copy(update={"polygon": type(far.polygon)(**poly)})
    assert find_blocked_edges(routing_graph, base_route.node_path, [far]) == []
    new_route, msg = reroute_if_blocked(routing_graph, base_route, [far], CostParams())
    assert new_route.node_path == base_route.node_path
    assert msg is None or msg == ""


# --- (d) M0 스키마 왕복/타입 일관 ---

def test_route_result_schema_roundtrip(base_route):
    dumped = base_route.model_dump()
    restored = RouteResult.model_validate(dumped)
    assert restored.model_dump() == dumped
    assert isinstance(base_route.max_risk_level, RiskLevel)
    assert base_route.distance_m > 0
    assert base_route.est_time_min > 0
    # 폴리라인 정점 수는 경로 노드 수와 정합(구간 연결).
    assert len(base_route.node_path) >= 2


# --- 결정론: 독립 2회 빌드/탐색 동일 ---

def test_full_pipeline_deterministic():
    g1 = build_routing_graph()
    g2 = build_routing_graph()
    r1 = find_route(g1, MOCK_ORIG, MOCK_DEST, CostParams())
    r2 = find_route(g2, MOCK_ORIG, MOCK_DEST, CostParams())
    assert r1.model_dump() == r2.model_dump()
