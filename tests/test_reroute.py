"""M4 동적 리라우팅 검증 — 공사/집회 폴리곤 교차 시 자동 재계산.

QA 관점(routing-engine SKILL 6장 + 검증 섹션과 공유):
1. 경로 위 공사 폴리곤 → 재계산되고, **새 경로는 폴리곤과 교차하지 않는다**.
2. 폴리곤 무관(경로 밖) → 원 경로 그대로 유지(재계산 없음).
3. 결정론: 같은 입력 2회 → 완전히 동일한 결과.

원칙:
- M3(`engine.routing`)은 재구현하지 않고 import해 쓴다(리라우팅은 얹기만).
- 좌표계 일치: 폴리곤(GeoJSON [lon,lat])과 엣지 라인을 같은 투영 CRS(UTM 52N, m)에서
  교차 판정한다. 이 파일의 검증도 `find_blocked_edges`(같은 CRS 경로)로 확인한다.

실행: `.venv/bin/python -m pytest tests/test_reroute.py -q`
"""

from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import networkx as nx
import pytest

from engine.reroute import (
    find_blocked_edges,
    kor_event_type,
    penalize_edges,
    reroute_if_blocked,
    route_diff,
)
from engine.routing import build_routing_graph, compute_edge_costs, find_route
from engine.schemas import (
    CostParams,
    DynamicEvent,
    EventType,
    RiskLevel,
)

SEOUL = ZoneInfo("Asia/Seoul")

# test_routing.py 와 동일한 실 OSM mock 노드(작은 클러스터).
MOCK_ORIG = 287284026
MOCK_DEST = 11153308710

CONSTRUCTION_ON_ROUTE_PATH = "data/mock/construction_on_route.json"


# ---------------------------------------------------------------------------
# 공유 fixture — 실 그래프 1회 구축, mock 이벤트 로드
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def routing_graph():
    return build_routing_graph()


@pytest.fixture(scope="module")
def base_route(routing_graph):
    """리라우팅 전 기준 경로(공사 폴리곤이 위에 놓이는 경로)."""
    route = find_route(routing_graph, MOCK_ORIG, MOCK_DEST, CostParams())
    assert route.reason is None
    return route


@pytest.fixture(scope="module")
def construction_event() -> DynamicEvent:
    """경로 위에 놓이는 공사 폴리곤(mock 파일에서 로드·파싱)."""
    with open(CONSTRUCTION_ON_ROUTE_PATH, encoding="utf-8") as f:
        return DynamicEvent(**json.load(f))


# ---------------------------------------------------------------------------
# 합성(toy) 그래프 — CRS/교차/우회를 통제된 조건에서 검증
# ---------------------------------------------------------------------------


def _toy_graph() -> nx.MultiDiGraph:
    """A→B 직선(짧음) vs A→C→B 우회. 좌표는 송파 인근 WGS84(경위도)."""
    G = nx.MultiDiGraph()
    G.add_node(1, x=127.100, y=37.500)  # A
    G.add_node(2, x=127.102, y=37.500)  # B (A와 같은 위도 → 직선은 lat=37.500)
    G.add_node(3, x=127.101, y=37.501)  # C (위쪽)

    def _add(u, v, length):
        for a, b in ((u, v), (v, u)):  # 양방향
            G.add_edge(
                a, b,
                length=length,
                shade_ratio=0.0,
                hazards=[],
                risk_level=RiskLevel.green.value,
                traffic=0.0,
            )

    _add(1, 2, length=180.0)   # 직선(짧음) — 폴리곤이 이 위에 놓인다
    _add(1, 3, length=160.0)   # 우회
    _add(3, 2, length=160.0)
    return G


def _toy_event(event_type: EventType = EventType.construction) -> DynamicEvent:
    """A→B 직선의 중점(127.101, 37.500)을 덮는 작은 폴리곤(경로 위)."""
    poly = {
        "type": "Polygon",
        "coordinates": [[
            [127.10080, 37.49990],
            [127.10120, 37.49990],
            [127.10120, 37.50010],
            [127.10080, 37.50010],
            [127.10080, 37.49990],
        ]],
    }
    return DynamicEvent(
        event_type=event_type,
        polygon=poly,
        start=datetime(2026, 7, 8, 7, 0, tzinfo=SEOUL),
        end=datetime(2026, 7, 8, 20, 0, tzinfo=SEOUL),
        source="toy",
    )


def _consecutive_pairs(node_path):
    return list(zip(node_path, node_path[1:]))


# ===========================================================================
# 1. 경로 위 공사 폴리곤 → 재계산 + 새 경로는 폴리곤과 교차하지 않음
# ===========================================================================


def test_construction_on_route_triggers_reroute_real_graph(
    routing_graph, base_route, construction_event
):
    """경로 위 공사 폴리곤 → 재계산되고, 새 경로는 폴리곤과 교차하지 않는다(실 그래프)."""
    G = routing_graph

    # 전제: 원 경로가 실제로 폴리곤과 교차한다.
    blocked_before = find_blocked_edges(G, base_route.node_path, [construction_event])
    assert blocked_before, "전제 실패: 공사 폴리곤이 원 경로 위에 있지 않다"

    new_route, msg = reroute_if_blocked(G, base_route, [construction_event], CostParams())

    # 재계산되어 경로가 바뀌었다.
    assert msg is not None
    assert new_route.reason is None
    assert new_route.node_path != base_route.node_path

    # 핵심: 새 경로는 폴리곤과 교차하지 않는다.
    blocked_after = find_blocked_edges(G, new_route.node_path, [construction_event])
    assert blocked_after == [], "재계산된 경로가 여전히 공사 폴리곤과 교차한다"

    # 출발/목적은 보존.
    assert new_route.node_path[0] == MOCK_ORIG
    assert new_route.node_path[-1] == MOCK_DEST
    # red 하드블록은 여전히 지켜진다.
    assert new_route.max_risk_level != RiskLevel.red


def test_reroute_writes_alert_and_diff_to_warnings(
    routing_graph, base_route, construction_event
):
    """변경 알림 문구 + 변경 diff(제외/신규 구간)가 RouteResult.warnings 에 담긴다."""
    new_route, msg = reroute_if_blocked(
        routing_graph, base_route, [construction_event], CostParams()
    )
    assert msg == "앞쪽 공사로 경로를 변경했어요"

    reroute_ws = [w for w in new_route.warnings if w.category == "reroute"]
    assert len(reroute_ws) >= 2, "리라우팅 알림/ diff 경고가 없다"
    # 알림 문구(정확히 msg)와 위치가 담긴 경고가 있다.
    assert any(w.message == msg and w.location is not None for w in reroute_ws)

    # diff 경고에 제외/신규 구간 수가 실제 diff와 일치한다.
    diff = route_diff(base_route.node_path, new_route.node_path)
    assert diff["removed"] and diff["added"]
    diff_msg = " ".join(w.message for w in reroute_ws)
    assert f"제외 {len(diff['removed'])}구간" in diff_msg
    assert f"신규 {len(diff['added'])}구간" in diff_msg


def test_toy_construction_on_direct_edge_forces_detour():
    """통제 그래프: 직선 위 공사 폴리곤 → C 경유 우회가 선택되고 폴리곤을 피한다."""
    G = _toy_graph()
    compute_edge_costs(G, CostParams())
    route = find_route(G, 1, 2, CostParams())
    assert route.node_path == [1, 2]  # 원래는 짧은 직선

    ev = _toy_event(EventType.construction)
    assert find_blocked_edges(G, route.node_path, [ev]), "전제: 직선이 폴리곤과 교차"

    new_route, msg = reroute_if_blocked(G, route, [ev], CostParams())
    assert msg == "앞쪽 공사로 경로를 변경했어요"
    assert new_route.node_path == [1, 3, 2]  # C 경유 우회
    assert find_blocked_edges(G, new_route.node_path, [ev]) == []
    assert (1, 2) not in _consecutive_pairs(new_route.node_path)


def test_toy_assembly_message_is_localized():
    """집회 이벤트면 알림 문구가 '집회'로 지역화된다."""
    G = _toy_graph()
    compute_edge_costs(G, CostParams())
    route = find_route(G, 1, 2, CostParams())
    ev = _toy_event(EventType.assembly)

    _, msg = reroute_if_blocked(G, route, [ev], CostParams())
    assert msg == "앞쪽 집회로 경로를 변경했어요"
    assert kor_event_type(EventType.assembly) == "집회"


def test_original_graph_not_mutated_by_reroute():
    """리라우팅은 원본 그래프를 변형하지 않는다(penalize_edges 는 copy)."""
    G = _toy_graph()
    compute_edge_costs(G, CostParams())
    cost_before = G[1][2][0]["cost"]

    route = find_route(G, 1, 2, CostParams())
    reroute_if_blocked(G, route, [_toy_event()], CostParams())

    assert G[1][2][0]["cost"] == cost_before  # 원본 cost 불변(inf로 안 바뀜)
    assert G[1][2][0]["cost"] != float("inf")


# ===========================================================================
# 2. 폴리곤 무관 → 원 경로 유지 (재계산 없음)
# ===========================================================================


def test_irrelevant_polygon_keeps_original_route_real_graph(routing_graph, base_route):
    """경로에서 먼 폴리곤 → 재계산 없이 원 경로/결과 그대로 반환."""
    far = DynamicEvent(
        event_type=EventType.construction,
        polygon={
            "type": "Polygon",
            "coordinates": [[
                [127.050, 37.440],
                [127.051, 37.440],
                [127.051, 37.441],
                [127.050, 37.441],
                [127.050, 37.440],
            ]],
        },
        start=datetime(2026, 7, 8, 7, 0, tzinfo=SEOUL),
        end=datetime(2026, 7, 8, 20, 0, tzinfo=SEOUL),
        source="far-away",
    )
    assert find_blocked_edges(routing_graph, base_route.node_path, [far]) == []

    out, msg = reroute_if_blocked(routing_graph, base_route, [far], CostParams())
    assert msg is None
    assert out is base_route  # 동일 객체를 그대로 반환(변경 없음)
    assert out.node_path == base_route.node_path


def test_empty_events_keeps_original_route(routing_graph, base_route):
    """이벤트가 없으면 원 경로 유지."""
    out, msg = reroute_if_blocked(routing_graph, base_route, [], CostParams())
    assert msg is None
    assert out.node_path == base_route.node_path


def test_inactive_time_window_keeps_original_route(
    routing_graph, base_route, construction_event
):
    """공사가 경로 위에 있어도 조회 시각이 활성 구간 밖이면 재계산하지 않는다."""
    # 이벤트 종료(20:00) 이후 시각.
    when = datetime(2026, 7, 8, 22, 0, tzinfo=SEOUL)
    out, msg = reroute_if_blocked(
        routing_graph, base_route, [construction_event], CostParams(), when=when
    )
    assert msg is None
    assert out.node_path == base_route.node_path


# ===========================================================================
# 3. 결정론 — 같은 입력 2회 동일
# ===========================================================================


def test_reroute_is_deterministic_same_graph(routing_graph, base_route, construction_event):
    """같은 그래프·경로·이벤트로 2회 리라우팅 → 완전히 동일한 결과."""
    r1, m1 = reroute_if_blocked(routing_graph, base_route, [construction_event], CostParams())
    r2, m2 = reroute_if_blocked(routing_graph, base_route, [construction_event], CostParams())
    assert m1 == m2
    assert r1.model_dump() == r2.model_dump()


def test_reroute_is_deterministic_across_independent_builds(construction_event):
    """독립적으로 두 번 구축한 그래프에서도 동일한 우회 경로(난수 없음)."""
    params = CostParams()
    g1 = build_routing_graph()
    g2 = build_routing_graph()
    base1 = find_route(g1, MOCK_ORIG, MOCK_DEST, params)
    base2 = find_route(g2, MOCK_ORIG, MOCK_DEST, params)

    r1, m1 = reroute_if_blocked(g1, base1, [construction_event], params)
    r2, m2 = reroute_if_blocked(g2, base2, [construction_event], params)
    assert m1 == m2
    assert r1.node_path == r2.node_path
    assert r1.distance_m == r2.distance_m
    assert r1.avg_shade_ratio == r2.avg_shade_ratio


def test_find_blocked_edges_is_deterministic(routing_graph, base_route, construction_event):
    """교차 판정 결과의 순서·내용이 매번 동일하다."""
    b1 = find_blocked_edges(routing_graph, base_route.node_path, [construction_event])
    b2 = find_blocked_edges(routing_graph, base_route.node_path, [construction_event])
    assert b1 == b2
    assert b1, "전제: 원 경로가 폴리곤과 교차"


# ===========================================================================
# 부가: penalize 모드(고가중) — 그래프 copy·cost 조정
# ===========================================================================


def test_penalize_mode_exclude_sets_inf_on_copy():
    """exclude 모드: 차단 엣지 cost=inf, 원본 불변(copy)."""
    G = _toy_graph()
    compute_edge_costs(G, CostParams())
    route = find_route(G, 1, 2, CostParams())
    blocked = find_blocked_edges(G, route.node_path, [_toy_event()])
    assert blocked

    G2 = penalize_edges(G, blocked, CostParams(), mode="exclude")
    for be in blocked:
        assert G2[be.u][be.v][be.k]["cost"] == float("inf")
        assert G[be.u][be.v][be.k]["cost"] != float("inf")  # 원본 불변
