"""M3 라우팅 엔진 검증 — 그래프 로드·비용함수 방향·hard-block·결정론.

QA 관점(routing-engine SKILL 검증 섹션과 공유):
1. 그래프 로드: 송파구 노드 수 > 0, 캐시 재사용(재다운로드 안 함).
2. 그늘 많은 우회 vs 짧은 뙤약볕 직선 → 그늘 경로 선택(비용함수 방향).
3. red 엣지 hard-block: 경로에 절대 포함되지 않음(위험하면 아무리 짧아도 안 감).
4. 결정론: 같은 입력 2회 → 동일 경로.

M1(그늘)·M2(위험)은 재구현하지 않고 실제 import해 연결한다:
- red 등급은 `engine.risk.compute_risk`가 산출한 값을 게이트에 넣는다.
- 실 그래프의 `shade_ratio`는 `engine.shade.compute_shade_ratios`가 채운다.

실행: `.venv/bin/python -m pytest tests/test_routing.py -q`
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import networkx as nx
import pytest

from engine.risk import compute_risk
from engine.routing import (
    build_routing_graph,
    compute_edge_costs,
    find_route,
    load_songpa_graph,
    neighborhood_loop,
    recommend_routes,
    safe_view,
)
from engine.schemas import (
    CostParams,
    EnvObservation,
    RiskLevel,
    RiskParams,
    Season,
)

SEOUL = ZoneInfo("Asia/Seoul")

# 송파 캐시 walk_graph에 실재하는 mock 노드(작은 클러스터, 그늘 엣지 포함).
MOCK_ORIG = 287284026
MOCK_DEST = 11153308710
EXPECTED_NODES = 9967
EXPECTED_EDGES = 28588


# ---------------------------------------------------------------------------
# 공유 fixture — 실 그래프는 한 번만 구축(로드+주입+비용)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def routing_graph():
    return build_routing_graph()


# ---------------------------------------------------------------------------
# 합성(toy) 그래프 — 비용함수 방향/게이트를 통제된 조건에서 검증
# ---------------------------------------------------------------------------


def _toy_two_route_graph(*, detour_shade: float) -> nx.MultiDiGraph:
    """A→B 직선(짧고 뙤약볕) vs A→C→B 우회(길고 그늘)인 통제 그래프.

    좌표는 실제와 무관한 배치용 값. 길이·그늘만 통제한다.
    """
    G = nx.MultiDiGraph()
    G.add_node(1, x=127.100, y=37.500)  # A
    G.add_node(2, x=127.102, y=37.500)  # B
    G.add_node(3, x=127.101, y=37.501)  # C

    def _add(u, v, length, shade):
        for a, b in ((u, v), (v, u)):  # 보행망은 양방향
            G.add_edge(
                a,
                b,
                length=length,
                shade_ratio=shade,
                hazards=[],
                risk_level=RiskLevel.green.value,
                traffic=0.0,
            )

    # 직선(1→2): 짧지만 그늘 0(뙤약볕).
    _add(1, 2, length=100.0, shade=0.0)
    # 우회(1→3→2): 더 길지만 그늘 많음.
    _add(1, 3, length=70.0, shade=detour_shade)
    _add(3, 2, length=70.0, shade=detour_shade)
    return G


def _toy_red_gate_graph() -> nx.MultiDiGraph:
    """A→B 직선이 red(위험), A→C→B 우회가 green인 통제 그래프.

    red 등급은 M2(compute_risk)로 실제 산출해 게이트에 넣는다(재구현 금지).
    """
    hot = EnvObservation(
        timestamp=datetime(2026, 7, 20, 14, 0, tzinfo=SEOUL),
        lat=37.5,
        lon=127.1,
        air_temp_c=36.0,
        humidity_pct=70.0,
        wind_ms=0.5,
        uv_index=9.0,
        pm10=40.0,
        pm25=20.0,
        road_surface_temp_c=63.0,  # 입력값: 발바닥 화상 임박 → M2 하드규칙 red
        season=Season.summer,
    )
    red_level = compute_risk(hot, RiskParams()).level
    assert red_level == RiskLevel.red  # 전제: M2가 실제로 red를 낸다

    G = nx.MultiDiGraph()
    G.add_node(1, x=127.100, y=37.500)  # A
    G.add_node(2, x=127.102, y=37.500)  # B
    G.add_node(3, x=127.101, y=37.501)  # C

    def _add(u, v, length, level):
        for a, b in ((u, v), (v, u)):
            G.add_edge(
                a, b,
                length=length,
                shade_ratio=0.0,
                hazards=[],
                risk_level=level.value,
                traffic=0.0,
            )

    _add(1, 2, length=50.0, level=red_level)      # 짧지만 위험(red)
    _add(1, 3, length=120.0, level=RiskLevel.green)
    _add(3, 2, length=120.0, level=RiskLevel.green)
    return G


def _consecutive_pairs(node_path):
    return list(zip(node_path, node_path[1:]))


# ---------------------------------------------------------------------------
# 1. 그래프 로드 + 캐시 재사용(재다운로드 금지)
# ---------------------------------------------------------------------------


def test_graph_loads_from_cache_without_redownload(monkeypatch):
    """캐시가 있으면 로드만 한다. OSM 다운로드가 호출되면 실패로 간주."""
    import osmnx as ox

    def _must_not_download(*args, **kwargs):
        raise AssertionError("캐시가 있는데 OSM 재다운로드를 시도했다")

    monkeypatch.setattr(ox, "graph_from_place", _must_not_download)

    G = load_songpa_graph()
    assert G.number_of_nodes() > 0
    assert G.number_of_nodes() == EXPECTED_NODES
    assert G.number_of_edges() == EXPECTED_EDGES


def test_injection_connects_m1_and_m2(routing_graph):
    """주입 결과가 M1(그늘>0인 엣지 존재)·M2(red 등급 엣지 존재)와 연결됐는지."""
    G = routing_graph
    shaded = sum(1 for _, _, d in G.edges(data=True) if d.get("shade_ratio", 0.0) > 0.0)
    reds = sum(
        1 for _, _, d in G.edges(data=True) if d.get("risk_level") == RiskLevel.red.value
    )
    assert shaded > 0, "M1 그늘이 어떤 엣지에도 반영되지 않았다"
    assert reds > 0, "M2 red 등급이 어떤 엣지에도 반영되지 않았다"
    # 모든 엣지에 cost가 계산돼 있어야 한다.
    assert all("cost" in d for _, _, d in G.edges(data=True))


# ---------------------------------------------------------------------------
# 2. 비용함수 방향 — 그늘 많은 우회가 짧은 뙤약볕을 이긴다
# ---------------------------------------------------------------------------


def test_shaded_detour_preferred_over_sunny_shortcut():
    """그늘 우회(A→C→B)가 짧은 뙤약볕 직선(A→B)보다 선택된다(shade_bonus 방향)."""
    params = CostParams()  # shade_bonus=0.4
    G = _toy_two_route_graph(detour_shade=1.0)
    compute_edge_costs(G, params)

    res = find_route(G, 1, 2, params)
    assert res.reason is None
    assert res.node_path == [1, 3, 2], "그늘 우회가 선택되지 않았다"
    assert res.avg_shade_ratio > 0.9


def test_no_shade_bonus_flips_to_shortest():
    """shade_bonus=0이면 그늘 유인이 사라져 짧은 직선(A→B)이 선택된다(방향 확인)."""
    params = CostParams(shade_bonus=0.0)
    G = _toy_two_route_graph(detour_shade=1.0)
    compute_edge_costs(G, params)

    res = find_route(G, 1, 2, params)
    assert res.node_path == [1, 2], "그늘 유인 제거 후에도 우회를 골랐다"


def test_find_route_honors_cost_params_recompute():
    """find_route에 준 CostParams가 실제 라우팅에 반영된다(비용 재계산).

    회귀 방지: 예전엔 find_route가 그래프에 구워진 `cost`만 읽어, 넘겨받은
    CostParams(예: shade_bonus)를 무시했다. 같은 그래프에서 미리 shade_bonus=0으로
    구워 둔 뒤 shade_bonus=0.4로 find_route를 부르면, 재계산이 되어야 그늘 우회가
    선택된다.
    """
    G = _toy_two_route_graph(detour_shade=1.0)  # 우회=그늘, 직선=뙤약볕
    compute_edge_costs(G, CostParams(shade_bonus=0.0))  # 버그 재현 조건: 그늘 무시로 구움

    r0 = find_route(G, 1, 2, CostParams(shade_bonus=0.0))
    assert r0.node_path == [1, 2]

    r1 = find_route(G, 1, 2, CostParams(shade_bonus=0.4))
    assert r1.node_path == [1, 3, 2], "find_route가 CostParams를 무시하고 구운 cost만 썼다(회귀)"
    assert r1.avg_shade_ratio > r0.avg_shade_ratio


def test_find_route_recompute_cost_false_uses_prebaked():
    """recompute_cost=False면 미리 구운 cost를 그대로 쓴다(리라우팅이 의존하는 경로)."""
    G = _toy_two_route_graph(detour_shade=1.0)
    compute_edge_costs(G, CostParams(shade_bonus=0.0))  # 직선이 최단이 되도록 구움
    # shade_bonus=0.4를 주더라도 recompute_cost=False면 구운 cost(그늘 무시)를 유지 → 직선.
    res = find_route(G, 1, 2, CostParams(shade_bonus=0.4), recompute_cost=False)
    assert res.node_path == [1, 2]


def test_recommend_routes_returns_distinct_shade_ranked_options():
    """여러 후보 경로를 그늘 많은 순으로, 실제 특성 라벨과 함께 반환한다."""
    G = _toy_two_route_graph(detour_shade=1.0)  # 그늘 우회 vs 뙤약볕 직선
    opts = recommend_routes(G, 1, 2)
    assert len(opts) >= 2, "서로 다른 후보가 최소 2개는 나와야(그늘 우회/최단)"
    labels = [o["label"] for o in opts]
    assert "그늘 최대" in labels and "최단 거리" in labels
    shades = [o["route"].avg_shade_ratio for o in opts]
    assert shades == sorted(shades, reverse=True), "그늘 많은 순 정렬"
    assert opts[0]["route"].node_path == [1, 3, 2]  # 그늘 최대 = 우회
    assert opts[0]["route"].avg_shade_ratio > opts[-1]["route"].avg_shade_ratio


# ---------------------------------------------------------------------------
# 3. red 엣지 hard-block — 경로에 포함되지 않는다
# ---------------------------------------------------------------------------


def test_red_edge_is_hard_blocked_in_toy_graph():
    """짧은 red 직선을 피해 green 우회로 돌아간다(위험하면 아무리 짧아도 안 감)."""
    params = CostParams()
    G = _toy_red_gate_graph()
    compute_edge_costs(G, params)

    res = find_route(G, 1, 2, params)
    assert res.reason is None
    assert res.node_path == [1, 3, 2]
    # red 직선 (1,2)가 경로에 없다.
    assert (1, 2) not in _consecutive_pairs(res.node_path)
    assert res.max_risk_level != RiskLevel.red


def test_only_red_path_returns_reason_not_exception():
    """유일한 경로가 red면 예외가 아니라 RouteResult(reason=...)."""
    params = CostParams()
    G = nx.MultiDiGraph()
    G.add_node(1, x=127.100, y=37.500)
    G.add_node(2, x=127.102, y=37.500)
    for a, b in ((1, 2), (2, 1)):
        G.add_edge(a, b, length=50.0, shade_ratio=0.0, hazards=[],
                   risk_level=RiskLevel.red.value, traffic=0.0)
    compute_edge_costs(G, params)

    res = find_route(G, 1, 2, params)
    assert res.node_path == []
    assert res.reason is not None


def test_real_graph_route_excludes_red_edges(routing_graph):
    """실 송파 그래프 경로에도 red 엣지가 포함되지 않는다."""
    params = CostParams()
    res = find_route(routing_graph, MOCK_ORIG, MOCK_DEST, params)
    assert res.reason is None
    assert res.max_risk_level != RiskLevel.red
    for u, v in _consecutive_pairs(res.node_path):
        best = min(
            routing_graph[u][v].values(),
            key=lambda d: d.get("cost", float("inf")),
        )
        assert best.get("risk_level") != RiskLevel.red.value


# ---------------------------------------------------------------------------
# 4. 결정론 — 같은 입력 2회 동일
# ---------------------------------------------------------------------------


def test_deterministic_same_graph_twice(routing_graph):
    params = CostParams()
    r1 = find_route(routing_graph, MOCK_ORIG, MOCK_DEST, params)
    r2 = find_route(routing_graph, MOCK_ORIG, MOCK_DEST, params)
    assert r1.model_dump() == r2.model_dump()


def test_deterministic_across_independent_builds():
    """독립적으로 두 번 구축(로드+주입+비용)해도 동일 경로가 나온다(난수 없음)."""
    params = CostParams()
    g1 = build_routing_graph()
    g2 = build_routing_graph()
    r1 = find_route(g1, MOCK_ORIG, MOCK_DEST, params)
    r2 = find_route(g2, MOCK_ORIG, MOCK_DEST, params)
    assert r1.node_path == r2.node_path
    assert r1.distance_m == r2.distance_m
    assert r1.est_time_min == r2.est_time_min
    assert r1.avg_shade_ratio == r2.avg_shade_ratio


# ---------------------------------------------------------------------------
# 부가: A* == Dijkstra, 동네 순환 루프
# ---------------------------------------------------------------------------


def test_astar_matches_dijkstra(routing_graph):
    params = CostParams()
    rd = find_route(routing_graph, MOCK_ORIG, MOCK_DEST, params, algorithm="dijkstra")
    ra = find_route(routing_graph, MOCK_ORIG, MOCK_DEST, params, algorithm="astar")
    assert rd.node_path == ra.node_path
    assert rd.distance_m == pytest.approx(ra.distance_m)


def test_neighborhood_loop_is_closed_and_near_target(routing_graph):
    params = CostParams()
    target = 1200.0
    loop = neighborhood_loop(routing_graph, MOCK_ORIG, target, params)
    assert loop.reason is None
    assert loop.node_path[0] == loop.node_path[-1] == MOCK_ORIG  # 출발=도착
    assert loop.distance_m > 0
    assert abs(loop.distance_m - target) / target <= 0.2  # target±20% 이내
    assert loop.max_risk_level != RiskLevel.red


def test_missing_node_returns_reason(routing_graph):
    params = CostParams()
    res = find_route(routing_graph, -1, MOCK_DEST, params)
    assert res.node_path == []
    assert res.reason is not None
