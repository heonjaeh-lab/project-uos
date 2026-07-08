"""M4 동적 리라우팅 패키지 — 공사/집회 폴리곤 교차 시 자동 재계산.

M3(`engine.routing`)을 **재구현하지 않고 import해** 얹는 얇은 계층이다. 활성 경로의
엣지가 신규 `DynamicEvent`(공사/집회) 폴리곤과 (같은 CRS에서) 교차하면 해당 엣지를
고가중/제외한 그래프로 재탐색하고, 변경 알림 문구와 변경 diff를 `RouteResult.warnings`에
담아 돌려준다. 결정론(난수 없음)·런타임 LLM 없음.

공개 API:
    from engine.reroute import (
        reroute_if_blocked,       # 메인: (route, msg) 반환
        find_blocked_edges,       # 교차하는 경로 엣지 탐지
        penalize_edges,           # 차단 엣지 고가중/제외(그래프 copy)
        route_edges, edge_line_wgs84, route_diff, kor_event_type,
        BlockedEdge,
        CRS_WGS84, CRS_SONGPA_METRIC,
    )

M5(개인화)/M6(게임화) 로직은 만들지 않는다. `params`/`walk_speed_m_per_min`/`env`/
`risk_params`/`pois` 주입구만 열어 M3로 그대로 전달한다.
"""

from __future__ import annotations

from engine.reroute.dynamic import (
    CRS_SONGPA_METRIC,
    CRS_WGS84,
    BlockedEdge,
    edge_line_wgs84,
    find_blocked_edges,
    kor_event_type,
    penalize_edges,
    reroute_if_blocked,
    route_diff,
    route_edges,
)

__all__ = [
    "reroute_if_blocked",
    "find_blocked_edges",
    "penalize_edges",
    "route_edges",
    "edge_line_wgs84",
    "route_diff",
    "kor_event_type",
    "BlockedEdge",
    "CRS_WGS84",
    "CRS_SONGPA_METRIC",
]
