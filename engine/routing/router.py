"""M3 경로 탐색 — 안전 게이트 + Dijkstra/A* + 경로 조립 + 동네 순환 루프.

핵심 원칙(routing-engine SKILL 4~5장):
- **최단이 아니라 가장 안전한** 경로. 비용은 `cost.edge_cost`(그늘 할인 + 위험/공사/
  집회/교통 가산)로 계산하고, red 등급 엣지는 **탐색에서 제외**(hard-block).
- 경로 없음은 예외가 아니라 `RouteResult(reason=...)`로 반환한다.
- 결정론: 난수 없음. networkx Dijkstra는 삽입 순서 tie-break라 같은 그래프면 동일.

`walk_speed_m_per_min`·`CostParams`·`RiskParams`는 주입(전역 상수 금지, M5 대비).
"""

from __future__ import annotations

import math
from typing import Any, Callable, Iterable

import networkx as nx

from engine.routing.cost import (
    CONSTRUCTION_TAG,
    DEFAULT_WALK_SPEED_M_PER_MIN,
    edge_cost,
)
from engine.schemas import (
    Coord,
    CostParams,
    GeoJSONLineString,
    POI,
    RiskLevel,
    RiskParams,
    RouteResult,
    RouteWarning,
    WarningLevel,
)

# 위험 등급 순서(집계용).
_RISK_ORDER = {RiskLevel.green: 0, RiskLevel.yellow: 1, RiskLevel.red: 2}

_NO_PATH_REASON = "안전 경로를 찾지 못했습니다 (위험 구간으로 단절)"
_MISSING_NODE_REASON = "출발/목적 노드가 그래프에 없습니다"


# ---------------------------------------------------------------------------
# 기하 헬퍼
# ---------------------------------------------------------------------------


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """두 WGS84 점 사이 대권 거리(m)."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearest_node(G, lat: float, lon: float) -> int:
    """좌표(WGS84)에 가장 가까운 그래프 노드 id.

    osmnx `nearest_nodes`는 미투영 그래프에서 scikit-learn을 요구하므로, 외부
    의존성 없이 haversine 최근접으로 직접 찾는다. 동률은 노드 id 오름차순(결정론).
    """
    best_id: int | None = None
    best_d = float("inf")
    for n, d in G.nodes(data=True):
        dist = _haversine_m(lat, lon, float(d["y"]), float(d["x"]))
        if dist < best_d or (dist == best_d and (best_id is None or n < best_id)):
            best_d = dist
            best_id = n
    if best_id is None:
        raise ValueError("그래프에 노드가 없습니다")
    return int(best_id)


# ---------------------------------------------------------------------------
# 안전 게이트 뷰
# ---------------------------------------------------------------------------


def _risk_str(value: Any) -> str:
    if isinstance(value, RiskLevel):
        return value.value
    return str(value)


def safe_view(G, params: CostParams):
    """hard-block 등급 엣지를 제외한 서브그래프 뷰(복사 없음).

    red(=`params.hard_block_level`) 엣지는 뷰에서 사라지므로 어떤 경로에도 포함될
    수 없다. 이것이 "위험한 길은 아무리 짧아도 안 감"의 강제 장치다.
    """

    def _keep_edge(u, v, k) -> bool:
        data = G[u][v][k]
        if _risk_str(data.get("risk_level", RiskLevel.green.value)) == params.hard_block_level:
            return False
        # cost가 계산돼 있으면 inf(=게이트/단절)도 배제.
        return data.get("cost", 0.0) != math.inf

    return nx.subgraph_view(G, filter_edge=_keep_edge)


# ---------------------------------------------------------------------------
# 엣지 조회·좌표
# ---------------------------------------------------------------------------


def _best_edge(G, u, v):
    """u→v 평행 엣지 중 최소 cost(없으면 최소 length) 엣지 dict과 방향(reversed) 반환."""
    if G.has_edge(u, v):
        keydict = G[u][v]
        rev = False
    elif G.has_edge(v, u):
        keydict = G[v][u]
        rev = True
    else:
        return None, False
    best = min(
        keydict.values(),
        key=lambda d: (d.get("cost", float("inf")), d.get("length", float("inf"))),
    )
    return best, rev


def _edge_coords(G, u, v, data, rev: bool) -> list[list[float]]:
    """엣지 폴리라인 [[lon,lat],...] (u→v 방향). geometry 없으면 노드 좌표 직선."""
    geom = data.get("geometry")
    if geom is not None and hasattr(geom, "coords"):
        coords = [[float(x), float(y)] for x, y in geom.coords]
    else:
        coords = [
            [float(G.nodes[u]["x"]), float(G.nodes[u]["y"])],
            [float(G.nodes[v]["x"]), float(G.nodes[v]["y"])],
        ]
    # u 노드에 더 가까운 끝이 앞으로 오도록 정렬(방향 일관성).
    ux, uy = float(G.nodes[u]["x"]), float(G.nodes[u]["y"])
    if coords:
        d_first = (coords[0][0] - ux) ** 2 + (coords[0][1] - uy) ** 2
        d_last = (coords[-1][0] - ux) ** 2 + (coords[-1][1] - uy) ** 2
        if d_last < d_first:
            coords = list(reversed(coords))
    return coords


# ---------------------------------------------------------------------------
# 경로 조립
# ---------------------------------------------------------------------------


def _max_risk(a: RiskLevel, b: RiskLevel) -> RiskLevel:
    return a if _RISK_ORDER[a] >= _RISK_ORDER[b] else b


def _pois_near(G, node_path: list[int], pois: Iterable[POI], radius_m: float) -> list[POI]:
    """경로 노드 반경 내 POI(입력 순서 유지, 중복 제거)."""
    coords = [(float(G.nodes[n]["y"]), float(G.nodes[n]["x"])) for n in node_path]
    out: list[POI] = []
    for poi in pois:
        for (nlat, nlon) in coords:
            if _haversine_m(nlat, nlon, poi.lat, poi.lon) <= radius_m:
                out.append(poi)
                break
    return out


def _build_warnings(
    hazards_seen: set[str],
    env,
    risk_params: RiskParams | None,
) -> list[RouteWarning]:
    warnings: list[RouteWarning] = []
    if "construction" in hazards_seen:
        warnings.append(
            RouteWarning(
                level=WarningLevel.warning,
                category="construction",
                message="경로에 공사 구간이 포함되어 있어요. 우회를 우선했습니다.",
            )
        )
    if "assembly" in hazards_seen:
        warnings.append(
            RouteWarning(
                level=WarningLevel.warning,
                category="assembly",
                message="경로에 집회 영향 구간이 있어요.",
            )
        )
    other = sorted(h for h in hazards_seen if h not in ("construction", "assembly"))
    if other:
        warnings.append(
            RouteWarning(
                level=WarningLevel.info,
                category="hazard",
                message=f"주의 구간이 있어요: {', '.join(other)}",
            )
        )
    # 환경(M2) 기반 열/노면 경고 — env가 주어질 때만.
    if env is not None and risk_params is not None:
        from engine.risk import compute_risk

        r = compute_risk(env, risk_params)
        if r.level != RiskLevel.green and r.dominant in ("heat", "surface"):
            cat = "surface" if r.dominant == "surface" else "heat"
            msg = (
                "노면이 뜨거워요. 발바닥 화상에 주의하세요."
                if cat == "surface"
                else "더위 지수가 높아요. 짧게·그늘 위주로 걸으세요."
            )
            warnings.append(
                RouteWarning(
                    level=WarningLevel.danger if r.level == RiskLevel.red else WarningLevel.warning,
                    category=cat,
                    message=msg,
                )
            )
    return warnings


def assemble_route(
    G,
    node_path: list[int],
    *,
    walk_speed_m_per_min: float = DEFAULT_WALK_SPEED_M_PER_MIN,
    env=None,
    risk_params: RiskParams | None = None,
    pois: Iterable[POI] | None = None,
    poi_radius_m: float = 150.0,
) -> RouteResult:
    """노드 경로 → `RouteResult`(거리·시간·평균그늘·최대위험·POI·경고).

    - `distance_m`: 엣지 `length` 합.
    - `est_time_min`: **실제 보행 시간**(= 거리 / 속도), 비용값 아님.
    - `avg_shade_ratio`: 길이 가중 평균 그늘.
    - `max_risk_level`: 경로 내 최대 위험 등급(red는 게이트로 제외되어 안 나옴).
    """
    if len(node_path) < 2:
        return RouteResult(node_path=[int(n) for n in node_path], reason=_NO_PATH_REASON)

    total_len = 0.0
    shade_weighted = 0.0
    max_risk = RiskLevel.green
    hazards_seen: set[str] = set()
    coords: list[list[float]] = []

    for u, v in zip(node_path, node_path[1:]):
        data, rev = _best_edge(G, u, v)
        if data is None:
            continue
        length_m = float(data.get("length", 0.0) or 0.0)
        total_len += length_m
        shade_weighted += float(data.get("shade_ratio", 0.0) or 0.0) * length_m
        try:
            rl = RiskLevel(_risk_str(data.get("risk_level", RiskLevel.green.value)))
        except ValueError:
            rl = RiskLevel.green
        max_risk = _max_risk(max_risk, rl)
        for h in data.get("hazards", []) or []:
            hazards_seen.add(h)
        seg = _edge_coords(G, u, v, data, rev)
        if not coords:
            coords.extend(seg)
        else:
            # 앞 구간 끝점과 겹치는 첫 정점은 건너뛴다.
            if seg and coords[-1] == seg[0]:
                coords.extend(seg[1:])
            else:
                coords.extend(seg)

    avg_shade = (shade_weighted / total_len) if total_len > 0 else 0.0
    avg_shade = max(0.0, min(1.0, avg_shade))
    est_time = total_len / walk_speed_m_per_min if walk_speed_m_per_min > 0 else 0.0

    polyline = None
    if len(coords) >= 2:
        polyline = GeoJSONLineString(coordinates=coords)

    pois_on = _pois_near(G, node_path, pois, poi_radius_m) if pois else []
    warnings = _build_warnings(hazards_seen, env, risk_params)

    return RouteResult(
        node_path=[int(n) for n in node_path],
        polyline=polyline,
        distance_m=total_len,
        est_time_min=est_time,
        avg_shade_ratio=avg_shade,
        max_risk_level=max_risk,
        pois_on_route=pois_on,
        warnings=warnings,
        reason=None,
    )


# ---------------------------------------------------------------------------
# 경로 탐색
# ---------------------------------------------------------------------------


def _astar_heuristic(G, params: CostParams, walk_speed_m_per_min: float) -> Callable:
    """admissible 휴리스틱: 직선거리 / 속도 × (달성 가능한 최소 배수).

    최소 배수 = max(0.1, 1 - shade_bonus): 그늘 할인만 최대로 받고 페널티 0인 경우의
    하한. 실제 남은 비용을 절대 초과하지 않으므로 admissible → A* 최적성 보장.
    """
    lower_mult = max(0.1, 1.0 - params.shade_bonus)

    def h(u: int, target: int) -> float:
        uy, ux = float(G.nodes[u]["y"]), float(G.nodes[u]["x"])
        ty, tx = float(G.nodes[target]["y"]), float(G.nodes[target]["x"])
        dist = _haversine_m(uy, ux, ty, tx)
        return (dist / walk_speed_m_per_min) * lower_mult

    return h


def find_route(
    G,
    orig_node: int,
    dest_node: int,
    params: CostParams,
    *,
    algorithm: str = "dijkstra",
    walk_speed_m_per_min: float = DEFAULT_WALK_SPEED_M_PER_MIN,
    recompute_cost: bool = True,
    env=None,
    risk_params: RiskParams | None = None,
    pois: Iterable[POI] | None = None,
) -> RouteResult:
    """`orig_node`→`dest_node` 최소비용(=가장 안전한) 경로.

    `recompute_cost=True`(기본)면 넘겨받은 `params`로 엣지 `cost`를 **다시 계산**한다.
    (그래야 find_route에 준 CostParams가 실제 라우팅에 반영된다 — params를 받으면서
    무시하던 함정 제거.) 비용을 이미 같은 params로 구워 뒀고 재계산 비용을 아끼려면
    `recompute_cost=False`. 경로가 없으면 예외 대신 `RouteResult(reason=...)`.
    """
    if orig_node not in G or dest_node not in G:
        return RouteResult(reason=_MISSING_NODE_REASON)

    if recompute_cost:
        from engine.routing.cost import compute_edge_costs
        compute_edge_costs(G, params, walk_speed_m_per_min=walk_speed_m_per_min)

    view = safe_view(G, params)
    try:
        if algorithm == "astar":
            path = nx.astar_path(
                view,
                orig_node,
                dest_node,
                heuristic=_astar_heuristic(view, params, walk_speed_m_per_min),
                weight="cost",
            )
        else:
            path = nx.shortest_path(view, orig_node, dest_node, weight="cost")
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return RouteResult(node_path=[], reason=_NO_PATH_REASON)

    return assemble_route(
        G,
        path,
        walk_speed_m_per_min=walk_speed_m_per_min,
        env=env,
        risk_params=risk_params,
        pois=pois,
    )


# ---------------------------------------------------------------------------
# 다중 경로 추천 (사용자가 지도에서 하나 선택)
# ---------------------------------------------------------------------------


def _label_routes(routes: list[RouteResult]) -> list[dict]:
    """서로 다른 경로들에 실제 특성 기준 라벨을 붙이고 그늘 많은 순 정렬."""
    if len(routes) == 1:
        return [{"label": "추천", "route": routes[0]}]
    shadiest = max(routes, key=lambda r: r.avg_shade_ratio)
    shortest = min(routes, key=lambda r: r.distance_m)
    out = []
    for r in routes:
        if r is shadiest:
            lab = "그늘 최대"
        elif r is shortest:
            lab = "최단 거리"
        else:
            lab = "균형"
        out.append({"label": lab, "route": r})
    out.sort(key=lambda x: -x["route"].avg_shade_ratio)
    return out


def recommend_routes(
    G,
    orig_node: int,
    dest_node: int,
    *,
    pois: Iterable[POI] | None = None,
    walk_speed_m_per_min: float = DEFAULT_WALK_SPEED_M_PER_MIN,
    max_routes: int = 3,
) -> list[dict]:
    """그늘↔거리 트레이드오프가 다른 후보 경로 **여러 개**를 반환(중복 제거).

    사용자가 지도에서 여러 안(그늘 최대/균형/최단)을 보고 하나를 골라 진행하도록
    한다. shade_bonus를 여러 단계로 돌려 서로 다른 경로만 모은다.

    Returns:
        list[{label, route}] — 그늘 많은 순. 후보가 없으면 빈 리스트.
    """
    seen: set[tuple] = set()
    found: list[RouteResult] = []
    for shade_bonus in (0.9, 0.5, 0.15, 0.0):
        r = find_route(G, orig_node, dest_node, CostParams(shade_bonus=shade_bonus),
                       walk_speed_m_per_min=walk_speed_m_per_min, pois=pois)
        if r.reason is not None:
            continue
        key = tuple(r.node_path)
        if key in seen:
            continue
        seen.add(key)
        found.append(r)
    if not found:
        return []
    return _label_routes(found)[:max_routes]


# ---------------------------------------------------------------------------
# 동네 순환 루프 (출발 = 목적)
# ---------------------------------------------------------------------------


def neighborhood_loop(
    G,
    start_node: int,
    target_m: float,
    params: CostParams,
    *,
    walk_speed_m_per_min: float = DEFAULT_WALK_SPEED_M_PER_MIN,
    max_candidates: int = 20,
    overlap_penalty: float = 4.0,
    recompute_cost: bool = True,
    env=None,
    risk_params: RiskParams | None = None,
    pois: Iterable[POI] | None = None,
) -> RouteResult:
    """출발=도착인 순환 산책 루프(목표 거리 `target_m`).

    접근(SKILL 5장): 출발 노드에서 `target_m/2` 반경의 turnaround 후보를 모아,
    각 후보로 **가는 길과 겹침이 적은** 왕복을 만들었을 때 총 길이가 target에 가장
    가깝고 그늘이 많은 루프를 고른다. 완전 최적화는 하지 않는다("target±20%면 충분").
    후보 정렬·tie-break는 노드 id 순으로 결정론이다.
    """
    if start_node not in G:
        return RouteResult(reason=_MISSING_NODE_REASON)

    if recompute_cost:
        from engine.routing.cost import compute_edge_costs
        compute_edge_costs(G, params, walk_speed_m_per_min=walk_speed_m_per_min)

    view = safe_view(G, params)
    if start_node not in view:
        return RouteResult(reason=_NO_PATH_REASON)

    sy, sx = float(G.nodes[start_node]["y"]), float(G.nodes[start_node]["x"])

    # 후보 turnaround: 출발에서 직선거리가 target의 0.15~0.35배인 노드(노드 id 오름차순).
    #   비겹침 왕복은 대략 왕복거리 ≈ 2.7~3배(반경)이라, 이 대역이 총 길이를 target
    #   근처로 맞춘다(실측상 편차 ~1%). 완전 최적화는 하지 않는다.
    candidates: list[int] = []
    for n in view.nodes:
        if n == start_node:
            continue
        ny, nx_ = float(G.nodes[n]["y"]), float(G.nodes[n]["x"])
        d = _haversine_m(sy, sx, ny, nx_)
        if 0.15 * target_m <= d <= 0.35 * target_m:
            candidates.append(n)
    candidates.sort()
    candidates = candidates[:max_candidates]

    def _return_weight(u, v, keydict):
        used = (frozenset((u, v)) in used_pairs)
        best = float("inf")
        for d in keydict.values():
            c = d.get("cost", float("inf"))
            if used and math.isfinite(c):
                c = c * overlap_penalty
            best = min(best, c)
        return best

    best_path: list[int] | None = None
    best_key: tuple | None = None

    for c in candidates:
        try:
            out = nx.shortest_path(view, start_node, c, weight="cost")
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            continue
        used_pairs = {frozenset((a, b)) for a, b in zip(out, out[1:])}
        try:
            back = nx.shortest_path(view, c, start_node, weight=_return_weight)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            continue
        loop = out + back[1:]
        # 길이·그늘 평가는 조립 결과로.
        res = assemble_route(G, loop, walk_speed_m_per_min=walk_speed_m_per_min)
        # 정렬 키: target 근접 우선, 그늘 많을수록, 노드 id 작을수록(결정론).
        key = (abs(res.distance_m - target_m), -res.avg_shade_ratio, c)
        if best_key is None or key < best_key:
            best_key = key
            best_path = loop

    if best_path is None:
        return RouteResult(node_path=[], reason="목표 거리에 맞는 순환 루프를 찾지 못했습니다")

    return assemble_route(
        G,
        best_path,
        walk_speed_m_per_min=walk_speed_m_per_min,
        env=env,
        risk_params=risk_params,
        pois=pois,
    )


# ---------------------------------------------------------------------------
# 다중 순환 루프 추천 (GPS 무목적지 모드 — recommend_routes의 순환판)
# ---------------------------------------------------------------------------


def _label_loops(loops: list[RouteResult]) -> list[dict]:
    """서로 다른 순환 루프들에 실제 특성 기준 라벨을 붙이고 그늘 많은 순 정렬.

    `_label_routes`와 같은 방식(결과 특성 기준, 변형 소스 기준이 아님). 단일
    후보로 collapse된 경우 목적지 왕복이 아니라 순환이므로 '추천' 대신 '동네
    순환'을 쓴다.
    """
    if len(loops) == 1:
        return [{"label": "동네 순환", "route": loops[0]}]
    shadiest = max(loops, key=lambda r: r.avg_shade_ratio)
    shortest = min(loops, key=lambda r: r.distance_m)
    out = []
    for r in loops:
        if r is shadiest:
            lab = "그늘 최대"
        elif r is shortest:
            lab = "짧은 순환"
        else:
            lab = "균형"
        out.append({"label": lab, "route": r})
    out.sort(key=lambda x: -x["route"].avg_shade_ratio)
    return out


def _try_loop(
    G,
    start_node: int,
    target_m: float,
    params: CostParams,
    *,
    walk_speed_m_per_min: float,
    pois: Iterable[POI] | None,
) -> RouteResult | None:
    """`neighborhood_loop` 1회 시도. 실패(빈 경로/예외)는 조용히 None."""
    try:
        loop = neighborhood_loop(
            G, start_node, target_m, params,
            walk_speed_m_per_min=walk_speed_m_per_min, pois=pois,
        )
    except Exception:
        return None
    if loop is None or loop.reason is not None or not loop.node_path:
        return None
    return loop


def recommend_loops(
    G,
    orig_node: int,
    target_m: float,
    pois: Iterable[POI] | None = None,
    *,
    cost_params: CostParams | None = None,
    walk_speed_m_per_min: float = DEFAULT_WALK_SPEED_M_PER_MIN,
    max_routes: int = 3,
) -> list[dict]:
    """GPS 무목적지(동네 순환) 모드용 — 순환 루프 **여러 변형**을 반환(중복 제거).

    `recommend_routes`(목적지 있는 경우)의 순환판. `neighborhood_loop`을 서로
    다른 `CostParams.shade_bonus`·목표 거리로 여러 번 호출해 그늘 많은 순환/
    균형 순환/짧은 순환처럼 서로 다른 루프만 모은다. 완전 최적화는 하지 않는다
    (target±20%면 충분 — neighborhood_loop과 동일 철학).

    변형이 특정 파라미터에서 실패(빈 경로/예외)하면 그 변형만 조용히 건너뛴다.
    모든 변형이 실패해도 기본 파라미터로 한 번 더 시도해 최소 1개는 반환한다
    (기존 단일 루프 폴백과 동등한 보장 — 무목적지 모드가 완전히 비는 일은 없다).

    Returns:
        list[{label, route}] — `recommend_routes`와 완전히 동일한 형식(route는
        `RouteResult`라 `route_payload`가 그대로 소비). 그늘 많은 순, `max_routes`
        (기본 3) 상한. 후보가 전혀 없으면 빈 리스트.
    """
    base = cost_params or CostParams()
    # (CostParams, 목표거리 배수) 변형 — 그늘 많은 순환 / 균형 순환(기본과 유사) /
    # 짧은 순환(그늘 유인 없음 + 목표거리도 줄임).
    variants: list[tuple[CostParams, float]] = [
        (base.model_copy(update={"shade_bonus": 0.9}), 1.0),
        (base.model_copy(update={"shade_bonus": 0.4}), 1.0),
        (base.model_copy(update={"shade_bonus": 0.0}), 0.75),
    ]

    seen: set[tuple] = set()
    found: list[RouteResult] = []
    for params, target_mult in variants:
        loop = _try_loop(
            G, orig_node, target_m * target_mult, params,
            walk_speed_m_per_min=walk_speed_m_per_min, pois=pois,
        )
        if loop is None:
            continue
        key = tuple(loop.node_path)
        if key in seen:
            continue
        seen.add(key)
        found.append(loop)

    if not found:
        # 모든 변형이 실패 — 기존 단일 루프 폴백과 동등하게 기본 파라미터로 한 번 더.
        loop = _try_loop(
            G, orig_node, target_m, base,
            walk_speed_m_per_min=walk_speed_m_per_min, pois=pois,
        )
        if loop is not None:
            found.append(loop)

    if not found:
        return []
    return _label_loops(found)[:max_routes]


__all__ = [
    "nearest_node",
    "safe_view",
    "assemble_route",
    "find_route",
    "neighborhood_loop",
    "recommend_loops",
]
