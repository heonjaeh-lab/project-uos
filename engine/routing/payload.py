"""라우팅 결과·보행 그래프 → 프론트 map_data 스키마(dict) 직렬화.

RouteResult와 그래프에서 프론트가 그대로 렌더할 수 있는 segs(그늘색 폴리라인 좌표열)·
POI·요약 통계를 뽑는다. export 스크립트(송파 데모)와 GPS 서버(서울 전역)가 **같은**
직렬화를 쓰도록 여기 한 곳에 둔다. 좌표는 [lon, lat](GeoJSON 순서)·소수점 6자리.
"""

from __future__ import annotations

import math

from engine.shade.sky import effective_shade


def edge_polyline(G, u, v) -> tuple[list[list[float]], float]:
    """엣지 (u,v)의 최저비용 평행엣지 geometry 좌표열 + 그늘비율.

    반환: ([[lon, lat], ...], shade_ratio). geometry가 없으면 두 노드를 잇는 직선.
    """
    best = min(G[u][v].values(), key=lambda d: d.get("cost", math.inf))
    geom = best.get("geometry")
    if geom is not None and hasattr(geom, "coords"):
        return [[round(x, 6), round(y, 6)] for x, y in geom.coords], float(best.get("shade_ratio", 0.0))
    return ([[round(float(G.nodes[u]["x"]), 6), round(float(G.nodes[u]["y"]), 6)],
             [round(float(G.nodes[v]["x"]), 6), round(float(G.nodes[v]["y"]), 6)]],
            float(best.get("shade_ratio", 0.0)))


def route_payload(G, r, label: str, clearness: float = 1.0) -> dict:
    """RouteResult → {label, shade, shade_eff, distance_m, est_time_min, max_risk, segs, pois}.

    segs 각 원소는 {line:[[lon,lat],...], shade, shade_eff} — 프론트가 그늘값으로 색칠한다.

    `shade`/`seg.shade` 는 **기하 그늘**(맑은 하늘 가정)로 불변이며, `shade_eff`/`seg.shade_eff`
    는 하늘 맑은 정도(`clearness` 0~1, 기본 1.0=맑음/현행)를 반영한 **실질 그늘**이다.
    clearness=1.0 이면 shade_eff == shade (회귀 없음). 흐릴수록 shade_eff 가 커진다.
    """
    segs = []
    for u, v in zip(r.node_path, r.node_path[1:]):
        line, sh = edge_polyline(G, u, v)
        segs.append({"line": line, "shade": sh,
                     "shade_eff": round(effective_shade(sh, clearness), 4)})
    return {"label": label, "shade": round(r.avg_shade_ratio, 3),
            "shade_eff": round(effective_shade(r.avg_shade_ratio, clearness), 3),
            "distance_m": round(r.distance_m), "est_time_min": round(r.est_time_min, 1),
            "max_risk": r.max_risk_level.value, "segs": segs,
            "pois": [{"lon": p.lon, "lat": p.lat, "type": p.poi_type.value, "name": p.name}
                     for p in r.pois_on_route]}


def routes_bbox(routes: list[dict], *, center: tuple[float, float] | None = None,
                pad: float = 0.003) -> list[float]:
    """경로들의 모든 정점을 덮는 [minlon, minlat, maxlon, maxlat] + 여백.

    경로가 없으면 center(lat, lon) 주변 기본 박스. center 미지정 시 0 박스.
    """
    xs = [p[0] for rt in routes for s in rt["segs"] for p in s["line"]]
    ys = [p[1] for rt in routes for s in rt["segs"] for p in s["line"]]
    if xs:
        return [min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad]
    if center is not None:
        lat, lon = center
        return [lon - 0.01, lat - 0.01, lon + 0.01, lat + 0.01]
    return [0.0, 0.0, 0.0, 0.0]


__all__ = ["edge_polyline", "route_payload", "routes_bbox"]
