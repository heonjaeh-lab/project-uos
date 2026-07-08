"""GPS 기반 로컬 라우팅 — 서울(및 전국) 어디서든 사용자 위치 주변만 온디맨드로.

전 지역을 메모리에 들지 않고, 요청 순간 GPS 주변 반경만 처리한다:
  1. `graph_from_point(GPS, dist)` 로 그 동네 보행망만 다운로드(타일 캐시)
  2. 그 bbox의 V-World 실측 건물로 그늘 계산(타일 캐시)
  3. 임의 좌표 실측 환경(build_env_at)으로 위험도 주입
  4. 다중 경로 추천 / 동네 순환

엔진(그늘·위험·라우팅)은 지역 독립적이라 그대로 재사용한다. 산책은 국지적(2~3km)이라
로컬 처리로 충분하며, 대규모에선 사전계산(배치→저장)으로 확장 가능하다.
"""

from __future__ import annotations

import math
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from engine.routing import (
    compute_edge_costs,
    inject_edge_attributes,
    nearest_node,
    neighborhood_loop,
    recommend_routes,
)
from engine.schemas import CostParams
from engine.sources import vworld

SEOUL = ZoneInfo("Asia/Seoul")
_GRAPH_DIR = "data/cache/local_graphs"
_BLDG_DIR = "data/cache/local_buildings"


def _haversine_m(lat1, lon1, lat2, lon2) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _tile_key(lat: float, lon: float, dist_m: float) -> str:
    return f"{lat:.3f}_{lon:.3f}_{int(dist_m)}"


def load_local_walk_graph(lat: float, lon: float, dist_m: float):
    """GPS 주변 반경 dist_m 보행망을 즉석 다운로드(타일 캐시). 재방문 지역은 즉시."""
    import osmnx as ox
    os.makedirs(_GRAPH_DIR, exist_ok=True)
    path = f"{_GRAPH_DIR}/{_tile_key(lat, lon, dist_m)}.graphml"
    if os.path.exists(path):
        return ox.load_graphml(path)
    graph = ox.graph_from_point((lat, lon), dist=int(dist_m), network_type="walk")
    ox.save_graphml(graph, path)
    return graph


def build_local_graph(lat: float, lon: float, *, dist_m: float = 1800,
                      when: datetime | None = None, env=None, cost_params=None,
                      use_real_env: bool = True):
    """GPS 주변 로컬 라우팅 그래프(보행망+실측건물 그늘+위험+비용). 반환 (G, buildings)."""
    when = when or datetime.now(SEOUL)
    G = load_local_walk_graph(lat, lon, dist_m)
    xs = [float(d["x"]) for _, d in G.nodes(data=True)]
    ys = [float(d["y"]) for _, d in G.nodes(data=True)]
    bbox = (min(xs), min(ys), max(xs), max(ys))
    os.makedirs(_BLDG_DIR, exist_ok=True)
    buildings = vworld.fetch_bbox(bbox, cache_path=f"{_BLDG_DIR}/{_tile_key(lat, lon, dist_m)}.json")
    if env is None and use_real_env:
        try:
            from engine.sources.weather import build_env_at
            env, _ = build_env_at(lat, lon, when)
        except Exception:
            env = None
    inject_edge_attributes(G, buildings=buildings, trees=[], shade_ref=(lat, lon),
                           when=when, env=env)
    compute_edge_costs(G, cost_params or CostParams())
    return G, buildings


def route_from_gps(lat: float, lon: float, dest: tuple[float, float] | None = None, *,
                   dist_m: float = 1800, target_m: float = 2000,
                   when: datetime | None = None, pois=None, cost_params=None) -> list[dict]:
    """사용자 GPS에서 경로 생성.

    - dest 지정: GPS→목적지 다중 경로(그늘/균형/최단). 그래프는 두 점을 덮도록 반경 자동 확장.
    - dest 없음: GPS 기준 동네 순환(목표 거리 target_m).
    반환: [{label, route}] (recommend_routes 형식).
    """
    if dest is not None:
        d = _haversine_m(lat, lon, dest[0], dest[1])
        radius = max(dist_m, d / 2 * 1.25 + 300)  # 두 끝점을 모두 덮는 반경
        clat, clon = (lat + dest[0]) / 2, (lon + dest[1]) / 2
        G, _ = build_local_graph(clat, clon, dist_m=radius, when=when, cost_params=cost_params)
        orig, dst = nearest_node(G, lat, lon), nearest_node(G, dest[0], dest[1])
        return recommend_routes(G, orig, dst, pois=pois)

    G, _ = build_local_graph(lat, lon, dist_m=max(dist_m, target_m * 0.7),
                             when=when, cost_params=cost_params)
    orig = nearest_node(G, lat, lon)
    loop = neighborhood_loop(G, orig, target_m, cost_params or CostParams(), pois=pois)
    return [{"label": "동네 순환", "route": loop}] if loop and loop.reason is None else []


__all__ = ["load_local_walk_graph", "build_local_graph", "route_from_gps"]
