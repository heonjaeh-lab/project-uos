"""M4 동적 리라우팅 — 활성 경로가 신규 공사/집회 폴리곤과 교차하면 자동 재계산.

routing-engine SKILL 6장 구현. 원칙:
- **M3 재구현 금지.** 경로 탐색·비용·조립은 `engine.routing`을 import해 그대로 쓴다.
  이 모듈은 "막힌 엣지를 골라 고가중/제외 → 재탐색 → 변경 알림·diff" 만 얹는다.
- **좌표계 일치(핵심).** 폴리곤(GeoJSON `[lon, lat]`, WGS84)과 엣지 라인(엣지
  geometry 또는 노드 `x`/`y`, 역시 WGS84)을 **같은 CRS로 투영**한 뒤 교차 판정한다.
  송파구 UTM 52N(EPSG:32652, 미터)로 투영해 shapely `intersects`로 본다. 교차는
  위상 불변량이라 어떤 CRS에서도 결과가 같지만, "같은 CRS" 규약을 코드로 강제해
  좌표 순서(lat/lon) 혼동을 원천 차단한다.
- **결정론.** 난수 없음. 투영·교차·정렬(엣지 id 순) 모두 재현 가능하다.
- **런타임 LLM 없음. 노면온도 등은 입력값**(추정하지 않음).
- **M5(개인화)/M6(게임화) 로직 없음.** `params`(CostParams)·`walk_speed_m_per_min`·
  `env`·`risk_params`·`pois` 주입구만 열어 둔다(그대로 M3로 전달).

전형적 사용:
    from engine.reroute import reroute_if_blocked
    new_route, msg = reroute_if_blocked(G, route, events, params)
    if msg:  # 변경됨 → new_route.warnings 에 알림 문구 + 변경 diff
        ...
"""

from __future__ import annotations

import math
from typing import Any, Iterable, NamedTuple

from pyproj import Transformer
from shapely.geometry import LineString, shape
from shapely.ops import transform as shp_transform

from engine.routing import (
    DEFAULT_WALK_SPEED_M_PER_MIN,
    find_route,
)
from engine.schemas import (
    Coord,
    CostParams,
    DynamicEvent,
    EventType,
    RiskParams,
    RouteResult,
    RouteWarning,
    WarningLevel,
)

# ---------------------------------------------------------------------------
# 좌표계(CRS) — 폴리곤과 엣지 라인을 반드시 같은 투영 CRS에서 비교한다
# ---------------------------------------------------------------------------

# 그래프 노드 x/y 와 GeoJSON coordinates 는 모두 WGS84(경위도)다.
CRS_WGS84 = "EPSG:4326"
# 송파구가 속한 UTM 52N(미터). 교차·버퍼는 이 투영 CRS(m)에서 수행한다.
CRS_SONGPA_METRIC = "EPSG:32652"

# always_xy=True → 입력/출력 좌표 순서를 (lon, lat)/(easting, northing)로 고정.
#   그래프 x=lon, y=lat 및 GeoJSON [lon, lat] 순서와 정확히 일치시킨다.
_TO_METRIC = Transformer.from_crs(CRS_WGS84, CRS_SONGPA_METRIC, always_xy=True)


def _to_metric(geom):
    """WGS84 shapely 지오메트리를 송파 UTM(m)으로 투영(결정론)."""
    return shp_transform(_TO_METRIC.transform, geom)


# 이벤트 종류 → 한국어(알림 문구용).
_KOR_EVENT = {
    EventType.construction: "공사",
    EventType.assembly: "집회",
}


def kor_event_type(event_type: Any) -> str:
    """EventType(또는 문자열) → 사용자 안내용 한국어 명칭."""
    if isinstance(event_type, EventType):
        return _KOR_EVENT[event_type]
    try:
        return _KOR_EVENT[EventType(str(event_type))]
    except (ValueError, KeyError):
        return str(event_type)


# ---------------------------------------------------------------------------
# 엣지 선택·라인화 (M3와 동일 규약: 경로가 실제로 쓰는 min-cost 엣지)
# ---------------------------------------------------------------------------


class BlockedEdge(NamedTuple):
    """차단(교차) 판정된 경로 엣지."""

    u: int
    v: int
    k: Any
    event_type: EventType
    event_index: int  # events 리스트 내 인덱스(설명용, 결정론)


def _best_edge_key(G, u, v):
    """u→v(없으면 v→u) 평행 엣지 중 경로가 실제 쓰는 min-cost 엣지 (data, key, rev)."""
    if G.has_edge(u, v):
        keydict, rev = G[u][v], False
    elif G.has_edge(v, u):
        keydict, rev = G[v][u], True
    else:
        return None, None, False
    best_k = min(
        keydict,
        key=lambda k: (
            keydict[k].get("cost", float("inf")),
            keydict[k].get("length", float("inf")),
            k,
        ),
    )
    return keydict[best_k], best_k, rev


def route_edges(G, node_path: list[int]) -> list[tuple[int, int, Any]]:
    """경로 노드열 → 실제 사용된 (u, v, k) 엣지 목록(M3 조립과 동일 선택 규약)."""
    edges: list[tuple[int, int, Any]] = []
    for u, v in zip(node_path, node_path[1:]):
        data, k, rev = _best_edge_key(G, u, v)
        if data is None:
            continue
        # 실제 진행 방향(u→v)의 엣지 식별자로 되돌린다.
        edges.append((v, u, k) if rev else (u, v, k))
    return edges


def edge_line_wgs84(G, u: int, v: int, k: Any = None) -> LineString:
    """엣지 폴리라인(WGS84, `[lon, lat]`). geometry 있으면 사용, 없으면 노드 직선.

    교차 판정 직전 `_to_metric`으로 투영되므로 반환은 WGS84 그대로다.
    """
    data = None
    if k is not None and G.has_edge(u, v) and k in G[u][v]:
        data = G[u][v][k]
    elif G.has_edge(u, v):
        # 방향 내 min-cost 엣지.
        keydict = G[u][v]
        bk = min(keydict, key=lambda kk: (keydict[kk].get("cost", float("inf")), kk))
        data = keydict[bk]
    geom = data.get("geometry") if data is not None else None
    if geom is not None and hasattr(geom, "coords"):
        return LineString([(float(x), float(y)) for x, y in geom.coords])
    return LineString(
        [
            (float(G.nodes[u]["x"]), float(G.nodes[u]["y"])),
            (float(G.nodes[v]["x"]), float(G.nodes[v]["y"])),
        ]
    )


def _edge_midpoint_coord(G, u: int, v: int) -> Coord:
    """엣지 중점(설명용 location). 노드 좌표 평균(WGS84)."""
    lat = (float(G.nodes[u]["y"]) + float(G.nodes[v]["y"])) / 2.0
    lon = (float(G.nodes[u]["x"]) + float(G.nodes[v]["x"])) / 2.0
    return Coord(lat=lat, lon=lon)


# ---------------------------------------------------------------------------
# 이벤트 활성 필터 + 교차 판정
# ---------------------------------------------------------------------------


def _active_events(events: Iterable[DynamicEvent], when) -> list[DynamicEvent]:
    """`when`(tz-aware)이 주어지면 활성 구간(start<=when<=end) 이벤트만. None이면 전부."""
    evs = list(events or [])
    if when is None:
        return evs
    out: list[DynamicEvent] = []
    for e in evs:
        try:
            if e.start <= when <= e.end:
                out.append(e)
        except TypeError:
            # tz naive/aware 혼용 등 비교 불가 → 보수적으로 포함.
            out.append(e)
    return out


def find_blocked_edges(
    G,
    node_path: list[int],
    events: Iterable[DynamicEvent],
    *,
    when=None,
    buffer_m: float = 0.0,
) -> list[BlockedEdge]:
    """경로 엣지 중 활성 이벤트 폴리곤과 교차하는 엣지 목록(결정론 정렬).

    폴리곤·엣지 라인을 **같은 투영 CRS(UTM 52N, m)** 로 옮겨 shapely `intersects`.
    `buffer_m`>0이면 폴리곤을 그만큼 미터 버퍼링해 근접 회피 여유를 준다.
    """
    active = _active_events(events, when)
    if not active or len(node_path) < 2:
        return []

    # 폴리곤을 1회씩만 투영(+버퍼) 해 캐시.
    metric_polys: list[tuple[int, EventType, Any]] = []
    for idx, e in enumerate(active):
        poly = _to_metric(shape(e.polygon.model_dump()))
        if buffer_m and buffer_m > 0:
            poly = poly.buffer(float(buffer_m))
        metric_polys.append((idx, e.event_type, poly))

    blocked: list[BlockedEdge] = []
    for (u, v, k) in route_edges(G, node_path):
        line_metric = _to_metric(edge_line_wgs84(G, u, v, k))
        for (idx, etype, poly) in metric_polys:
            if line_metric.intersects(poly):
                blocked.append(BlockedEdge(u=u, v=v, k=k, event_type=etype, event_index=idx))
    # 결정론 정렬: (u, v, event_index).
    blocked.sort(key=lambda b: (int(b.u), int(b.v), b.event_index))
    return blocked


# ---------------------------------------------------------------------------
# 막힌 엣지 고가중/제외
# ---------------------------------------------------------------------------


def penalize_edges(
    G,
    blocked: Iterable[BlockedEdge],
    params: CostParams,
    *,
    mode: str = "exclude",
    walk_speed_m_per_min: float = DEFAULT_WALK_SPEED_M_PER_MIN,
):
    """차단 엣지의 `cost`를 조정한 **새 그래프(copy)** 반환(원본 G 불변).

    - `mode="exclude"`(기본): 차단 엣지 `cost=inf` → M3 `safe_view`가 탐색에서 제외.
      "새 경로는 폴리곤과 교차하지 않는다"를 보장하는 강한 모드.
    - `mode="penalize"`(고가중): 차단 엣지에 이벤트 페널티(construction/assembly)를
      더해 `cost`를 재계산. 대안이 정말 없으면 통과할 수 있다(soft).
    """
    from engine.routing import edge_cost  # M3 비용함수 재사용(재구현 금지).

    G2 = G.copy()
    for be in blocked:
        if not G2.has_edge(be.u, be.v) or be.k not in G2[be.u][be.v]:
            continue
        d = G2[be.u][be.v][be.k]
        if mode == "penalize":
            tags = list(d.get("hazards", []) or [])
            tag = be.event_type.value  # "construction" | "assembly"
            if tag not in tags:
                tags = tags + [tag]
            d["cost"] = edge_cost(
                length_m=float(d.get("length", 0.0) or 0.0),
                shade_ratio=float(d.get("shade_ratio", 0.0) or 0.0),
                hazards=tags,
                risk_level=d.get("risk_level", "green"),
                traffic=float(d.get("traffic", 0.0) or 0.0),
                params=params,
                walk_speed_m_per_min=walk_speed_m_per_min,
            )
        else:  # exclude
            d["cost"] = math.inf
    return G2


# ---------------------------------------------------------------------------
# 변경 diff (설명 가능성)
# ---------------------------------------------------------------------------


def _undirected_pairs(node_path: list[int]) -> list[frozenset]:
    return [frozenset((a, b)) for a, b in zip(node_path, node_path[1:])]


def _ordered_pairs(node_path: list[int]) -> list[tuple[int, int]]:
    return [(int(a), int(b)) for a, b in zip(node_path, node_path[1:])]


def route_diff(old_path: list[int], new_path: list[int]) -> dict[str, list[tuple[int, int]]]:
    """옛 경로 대비 신 경로의 제외/신규 구간(무방향 비교, 결정론 정렬)."""
    old_set = set(_undirected_pairs(old_path))
    new_set = set(_undirected_pairs(new_path))
    removed = [p for p in _ordered_pairs(old_path) if frozenset(p) not in new_set]
    added = [p for p in _ordered_pairs(new_path) if frozenset(p) not in old_set]
    return {"removed": removed, "added": added}


# ---------------------------------------------------------------------------
# 메인 진입점
# ---------------------------------------------------------------------------


def reroute_if_blocked(
    G,
    route: RouteResult,
    events: Iterable[DynamicEvent],
    params: CostParams,
    *,
    when=None,
    mode: str = "exclude",
    buffer_m: float = 0.0,
    max_iterations: int = 8,
    walk_speed_m_per_min: float = DEFAULT_WALK_SPEED_M_PER_MIN,
    env=None,
    risk_params: RiskParams | None = None,
    pois=None,
) -> tuple[RouteResult, str | None]:
    """활성 경로가 공사/집회 폴리곤과 교차하면 재탐색해 우회 경로를 돌려준다.

    Returns:
        (route_out, msg):
          - 교차 없음 → (원 route, None)  (변경 없음)
          - 교차 있음 → (새 route, "앞쪽 …로 경로를 변경했어요")
            새 route.warnings 에 리라우팅 알림 + 변경 diff(제외/신규 구간)를 담는다.

    `exclude` 모드는 재탐색 후에도 다른 엣지가 폴리곤과 겹치면 그 엣지까지 반복 제외해
    "새 경로는 폴리곤과 교차하지 않음"을 보장한다(대안이 있으면). 대안이 없으면
    `reason`이 채워진 실패 RouteResult를 그대로 반환한다.
    """
    # 유효하지 않은/빈 경로는 그대로.
    if route is None or route.reason is not None or len(route.node_path) < 2:
        return route, None

    active = _active_events(events, when)
    first_blocked = find_blocked_edges(G, route.node_path, active, buffer_m=buffer_m)
    if not first_blocked:
        return route, None  # 폴리곤 무관 → 원 경로 유지.

    orig, dest = int(route.node_path[0]), int(route.node_path[-1])
    G2 = G.copy()
    # find_route가 이제 params로 cost를 재계산하므로(정직한 API), 리라우팅은
    # 페널티를 스스로 관리한다: 여기서 base cost를 params로 한 번 굽고, 루프의
    # find_route는 recompute_cost=False 로 호출해 penalize가 심은 inf/페널티를 보존한다.
    from engine.routing import compute_edge_costs
    compute_edge_costs(G2, params, walk_speed_m_per_min=walk_speed_m_per_min)
    accumulated: list[BlockedEdge] = []
    current = route

    for _ in range(max_iterations):
        blocked_now = find_blocked_edges(G2, current.node_path, active, buffer_m=buffer_m)
        if not blocked_now:
            break
        accumulated.extend(blocked_now)
        G2 = penalize_edges(
            G2,
            blocked_now,
            params,
            mode=mode,
            walk_speed_m_per_min=walk_speed_m_per_min,
        )
        current = find_route(
            G2,
            orig,
            dest,
            params,
            walk_speed_m_per_min=walk_speed_m_per_min,
            recompute_cost=False,  # penalize_edges가 심은 inf/페널티를 보존
            env=env,
            risk_params=risk_params,
            pois=pois,
        )
        if current.reason is not None:  # 우회 불가 → 실패 결과 반환.
            break

    # 알림 문구: 첫(정렬상 가장 앞) 차단 이벤트 종류 기준.
    lead = accumulated[0]
    msg = f"앞쪽 {kor_event_type(lead.event_type)}로 경로를 변경했어요"

    # 실패(우회 경로 없음)면 알림만 남기고 반환.
    if current.reason is not None:
        current.warnings = [
            RouteWarning(
                level=WarningLevel.danger,
                category="reroute",
                message=f"앞쪽 {kor_event_type(lead.event_type)} 구간을 우회할 경로를 찾지 못했어요",
                location=_edge_midpoint_coord(G, lead.u, lead.v),
            )
        ] + list(current.warnings)
        return current, msg

    # 변경 diff 계산 → warnings 에 설명 가능하게 적재.
    diff = route_diff(route.node_path, current.node_path)
    blocked_pairs = sorted({(int(b.u), int(b.v)) for b in accumulated})
    kinds = sorted({kor_event_type(b.event_type) for b in accumulated})

    reroute_warnings = [
        RouteWarning(
            level=WarningLevel.warning,
            category="reroute",
            message=msg,
            location=_edge_midpoint_coord(G, lead.u, lead.v),
        ),
        RouteWarning(
            level=WarningLevel.info,
            category="reroute",
            message=(
                f"경로 변경: {'/'.join(kinds)} 구간 {len(blocked_pairs)}개 회피 "
                f"(제외 {len(diff['removed'])}구간, 신규 {len(diff['added'])}구간). "
                f"차단 엣지 {blocked_pairs}, 제외 {diff['removed']}, 신규 {diff['added']}"
            ),
        ),
    ]
    current.warnings = reroute_warnings + list(current.warnings)
    return current, msg


__all__ = [
    "CRS_WGS84",
    "CRS_SONGPA_METRIC",
    "kor_event_type",
    "BlockedEdge",
    "route_edges",
    "edge_line_wgs84",
    "find_blocked_edges",
    "penalize_edges",
    "route_diff",
    "reroute_if_blocked",
]
