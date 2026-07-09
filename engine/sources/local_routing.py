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
    recommend_loops,
    recommend_routes,
)
from engine.schemas import CostParams, RiskParams
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
    - dest 없음: GPS 기준 동네 순환 다중 변형(목표 거리 target_m, 그늘/균형/짧은 순환).
    반환: [{label, route}] (recommend_routes/recommend_loops 공용 형식).
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
    return recommend_loops(G, orig, target_m, pois, cost_params=cost_params or CostParams())


def _weather_meta(env, hourly: list[dict], adv) -> dict:
    """env·hourly·advisory → meta dict. `gps_map_payload`/`weather_payload` 공용
    (중복 제거 — 스키마 표류 방지). now_* 필드는 항상 hourly[0] 기준."""
    return {
        "now_score": hourly[0]["score"] if hourly else None,
        "now_level": hourly[0]["level"] if hourly else None,
        "now_dominant": hourly[0]["dominant"] if hourly else None,
        "advisory": adv.status,
        "advisory_reason": adv.reason,
        "rain": adv.rain,
        "air_temp_c": env.air_temp_c,
        "humidity_pct": env.humidity_pct,
        "pm10": env.pm10,
        "precip_prob_pct": env.precip_prob_pct,
    }


def gps_map_payload(lat: float, lon: float, dest: tuple[float, float] | None = None, *,
                    dist_m: float = 1800, target_m: float = 2000,
                    when: datetime | None = None, pois=None, cost_params=None,
                    hours: int = 12, risk_params: RiskParams | None = None) -> dict:
    """사용자 GPS(+선택 목적지)에서 프론트 map_data.json과 **동일 스키마** dict 생성.

    export_map_data(송파 데모)와 같은 필드를 서울 전역 임의 좌표로 낸다:
      routes(다중/순환) · bbox · gps · origin · dest · hourly · meta.
    프론트가 이 dict로 DATA를 교체하면 그대로 렌더된다. context(배경 도로망)는
    Leaflet 실 타일이 대체하므로 뺀다(payload·계산 절감).

    risk_params(선택, M5 개인화 `profile_to_risk_params` 결과)를 주면 hourly/meta의
    위험지수·산책 권고가 개인화된다. 라우팅 비용(그래프 비용함수)은 이번 범위에서
    개인화하지 않는다(CostParams는 그대로) — 견종별 라우팅 반영은 별도 과제.
    """
    from engine.risk import walk_advisory
    from engine.routing import route_payload, routes_bbox
    from engine.sources.weather import build_env_at, hourly_risk_series

    when = when or datetime.now(SEOUL)
    # 사용자 위치 실측 환경(그래프 그늘/위험 주입 + meta 공용). dest여도 GPS 기준.
    env, missing = build_env_at(lat, lon, when)

    if dest is not None:
        d = _haversine_m(lat, lon, dest[0], dest[1])
        radius = max(dist_m, d / 2 * 1.25 + 300)
        clat, clon = (lat + dest[0]) / 2, (lon + dest[1]) / 2
        G, _ = build_local_graph(clat, clon, dist_m=radius, when=when, env=env,
                                 cost_params=cost_params)
        orig, dst = nearest_node(G, lat, lon), nearest_node(G, dest[0], dest[1])
        opts = recommend_routes(G, orig, dst, pois=pois)
    else:
        G, _ = build_local_graph(lat, lon, dist_m=max(dist_m, target_m * 0.7),
                                 when=when, env=env, cost_params=cost_params)
        orig = nearest_node(G, lat, lon)
        opts = recommend_loops(G, orig, target_m, pois, cost_params=cost_params or CostParams())
        dst = orig

    routes = [route_payload(G, o["route"], o["label"]) for o in opts]
    for i, r in enumerate(routes):
        r["id"] = f"r{i}"  # 프론트가 인덱스 대신 안정적 id로 경로를 선택할 수 있게.
    bbox = routes_bbox(routes, center=(lat, lon))
    hourly = hourly_risk_series(when=when, hours=hours, lat=lat, lon=lon, params=risk_params)
    adv = walk_advisory(env, missing=missing, params=risk_params)
    return {
        "bbox": bbox,
        "gps": {"lon": lon, "lat": lat},
        "origin": [round(float(G.nodes[orig]["x"]), 6), round(float(G.nodes[orig]["y"]), 6)],
        "dest": [round(float(G.nodes[dst]["x"]), 6), round(float(G.nodes[dst]["y"]), 6)],
        "routes": routes,
        "hourly": hourly,
        "meta": _weather_meta(env, hourly, adv),
    }


def weather_payload(lat: float, lon: float, *, when: datetime | None = None,
                    hours: int = 12, params: RiskParams | None = None) -> dict:
    """경량 날씨/위험지수 payload — 그래프·OSM·V-World를 **호출하지 않는다**.

    `build_env_at`+`hourly_risk_series`+`walk_advisory`만 호출해 `{"meta", "hourly"}`를
    낸다(그늘/라우팅 없이 가벼움 — `/api/weather`용). `gps_map_payload`와 meta 조립
    로직(`_weather_meta`)을 공유해 두 스키마가 표류하지 않도록 한다.
    """
    from engine.risk import walk_advisory
    from engine.sources.weather import build_env_at, hourly_risk_series

    when = when or datetime.now(SEOUL)
    env, missing = build_env_at(lat, lon, when)
    hourly = hourly_risk_series(when=when, hours=hours, lat=lat, lon=lon, params=params)
    adv = walk_advisory(env, missing=missing, params=params)
    return {"meta": _weather_meta(env, hourly, adv), "hourly": hourly}


__all__ = ["load_local_walk_graph", "build_local_graph", "route_from_gps", "gps_map_payload",
           "weather_payload"]
