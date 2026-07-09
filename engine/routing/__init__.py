"""M3 라우팅 엔진 패키지 — 안전 경로 추천.

송파구 실 OSM 보행망(캐시)에 M1(그늘)·M2(위험지수) 결과와 mock 위험요소를 얹고,
그늘 할인·위험/공사/집회/교통 가산·red 하드블록을 반영한 비용함수로 **최단이 아니라
가장 안전한** 경로를 찾는다. 결정론(난수 없음)·런타임 LLM 없음.

공개 API:
    from engine.routing import (
        # 그래프 구축
        load_songpa_graph, inject_edge_attributes, build_routing_graph,
        default_summer_env, default_when,
        # 비용함수
        edge_cost, compute_edge_costs, DEFAULT_WALK_SPEED_M_PER_MIN,
        # 탐색
        nearest_node, find_route, assemble_route, neighborhood_loop, recommend_loops,
        safe_view,
    )

M5(개인화)/M6(게임화) 로직은 이번 범위에서 만들지 않는다. `CostParams`/`RiskParams`/
`ShadeParams`·`walk_speed_m_per_min` 주입구만 열어 둔다.
"""

from __future__ import annotations

from engine.routing.cost import (
    ASSEMBLY_TAG,
    CONSTRUCTION_TAG,
    DEFAULT_WALK_SPEED_M_PER_MIN,
    compute_edge_costs,
    edge_cost,
)
from engine.routing.graph_build import (
    BUILDINGS_PATH,
    DEFAULT_GRAPH_PATH,
    TREES_PATH,
    build_routing_graph,
    default_summer_env,
    default_when,
    inject_edge_attributes,
    load_songpa_graph,
)
from engine.routing.payload import edge_polyline, route_payload, routes_bbox
from engine.routing.router import (
    assemble_route,
    find_route,
    nearest_node,
    neighborhood_loop,
    recommend_loops,
    recommend_routes,
    safe_view,
)

__all__ = [
    # cost
    "edge_cost",
    "compute_edge_costs",
    "DEFAULT_WALK_SPEED_M_PER_MIN",
    "CONSTRUCTION_TAG",
    "ASSEMBLY_TAG",
    # graph_build
    "load_songpa_graph",
    "inject_edge_attributes",
    "build_routing_graph",
    "default_summer_env",
    "default_when",
    "DEFAULT_GRAPH_PATH",
    "BUILDINGS_PATH",
    "TREES_PATH",
    # router
    "nearest_node",
    "find_route",
    "recommend_routes",
    "assemble_route",
    "neighborhood_loop",
    "recommend_loops",
    "safe_view",
    # payload
    "edge_polyline",
    "route_payload",
    "routes_bbox",
]
