"""실데이터 구동 데모 — 송파구 실 OSM 보행망 + 실 건물 그림자 + 실 POI로
안전 경로를 계산하고, 안전(그늘/위험 반영) vs 최단 경로를 비교한다.

실행: PYTHONPATH=. .venv/bin/python scripts/run_real_songpa.py
"""

from __future__ import annotations

import json
import math
import os
import time

from engine.routing import find_route
from engine.schemas import CostParams
from engine.sources import osm
from engine.sources.real_graph import build_real_routing_graph

# 송파구 내 두 지점(약 2km) — 잠실 인근 → 올림픽공원 인근.
ORIG_LATLON = (37.5133, 127.1001)
DEST_LATLON = (37.5215, 127.1215)
OUT_GEOJSON = "data/demo/real_route.geojson"


def _haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearest_node(G, lat, lon):
    best, bestd = None, float("inf")
    for n, d in G.nodes(data=True):
        dist = _haversine_m(lat, lon, float(d["y"]), float(d["x"]))
        if dist < bestd:
            best, bestd = n, dist
    return best


def route_geojson(G, route, pois):
    coords = [[float(G.nodes[n]["x"]), float(G.nodes[n]["y"])] for n in route.node_path]
    feats = [{
        "type": "Feature",
        "properties": {"kind": "route", "distance_m": route.distance_m,
                       "est_time_min": route.est_time_min,
                       "avg_shade_ratio": route.avg_shade_ratio,
                       "max_risk_level": route.max_risk_level.value},
        "geometry": {"type": "LineString", "coordinates": coords},
    }]
    for p in pois:
        feats.append({
            "type": "Feature",
            "properties": {"kind": "poi", "poi_type": p.poi_type.value, "name": p.name},
            "geometry": {"type": "Point", "coordinates": [p.lon, p.lat]},
        })
    return {"type": "FeatureCollection", "features": feats}


def main():
    t0 = time.time()
    G, buildings, trees, env, missing = build_real_routing_graph()
    t_build = time.time() - t0

    # 오늘의 산책 위험지수 (실측 기상·대기질 기반, 송파구 전역)
    if env is not None:
        from engine.risk import compute_risk
        from engine.schemas import RiskParams
        r = compute_risk(env, RiskParams(), missing=missing)
        print(f"[오늘의 산책 위험지수] {r.score:.0f}점 · {r.level.value.upper()} · 주요인 {r.dominant} "
              f"(실측: 기온 {env.air_temp_c}℃·습도 {env.humidity_pct}%·PM10 {env.pm10:.0f}·PM2.5 {env.pm25:.0f}"
              f" / 결측중립 {sorted(missing)})")

    print(f"[그래프] 실데이터 주입 완료 — 건물 {len(buildings)} · 가로수 {len(trees)} "
          f"· 노드 {G.number_of_nodes()} · 엣지 {G.number_of_edges()} · {t_build:.1f}s")

    shaded = [d["shade_ratio"] for _, _, d in G.edges(data=True) if d.get("shade_ratio", 0) > 0]
    avg = sum(shaded) / len(shaded) if shaded else 0.0
    print(f"[그늘] shade_ratio>0 엣지 {len(shaded)}개 "
          f"({100*len(shaded)/G.number_of_edges():.1f}%), 평균 {avg:.3f} "
          f"(실제 송파구 건물 {len(buildings)}개 그림자 기반)")

    pois = osm.fetch_pois()
    orig = nearest_node(G, *ORIG_LATLON)
    dest = nearest_node(G, *DEST_LATLON)
    print(f"[경로] 출발 {ORIG_LATLON}→node {orig} / 도착 {DEST_LATLON}→node {dest}")

    # 그늘 효과 격리: 다른 조건(위험/교통 페널티) 동일, shade_bonus만 on/off.
    safe = find_route(G, orig, dest, CostParams(), pois=pois)             # 그늘 선호(bonus=0.4)
    noshade = find_route(G, orig, dest, CostParams(shade_bonus=0.0), pois=pois)  # 그늘 무시
    print("\n── 안전 경로(그늘 선호, bonus=0.4) ──")
    _print_route(safe)
    print("── 그늘 무시 경로(비교용, bonus=0.0) ──")
    _print_route(noshade)
    print(f"\n비교(그늘 격리): 그늘선호 {safe.distance_m:.0f}m/그늘{safe.avg_shade_ratio:.3f} "
          f"vs 그늘무시 {noshade.distance_m:.0f}m/그늘{noshade.avg_shade_ratio:.3f} "
          f"→ 그늘 {safe.avg_shade_ratio - noshade.avg_shade_ratio:+.3f}, "
          f"거리 {safe.distance_m - noshade.distance_m:+.0f}m")

    os.makedirs(os.path.dirname(OUT_GEOJSON), exist_ok=True)
    with open(OUT_GEOJSON, "w", encoding="utf-8") as f:
        json.dump(route_geojson(G, safe, safe.pois_on_route), f, ensure_ascii=False)
    print(f"\n[출력] 안전 경로 GeoJSON → {OUT_GEOJSON} (geojson.io 등에 붙여 눈으로 확인)")


def _print_route(r):
    if r.reason:
        print(f"  경로 없음: {r.reason}")
        return
    from collections import Counter
    c = Counter(p.poi_type.value for p in r.pois_on_route)
    print(f"  거리 {r.distance_m:.0f}m · 시간 {r.est_time_min:.1f}min · "
          f"평균그늘 {r.avg_shade_ratio:.3f} · 최대위험 {r.max_risk_level.value} · "
          f"경유노드 {len(r.node_path)} · 경로변 POI {len(r.pois_on_route)} {dict(c)}")


if __name__ == "__main__":
    main()
