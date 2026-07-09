"""오늘의 경로 지도(대화형) 데이터 추출 → data/demo/map_data.json.

- gps: 사용자 GPS 위치(원점) → 최근접 보행 노드로 자동 매칭
- routes: 다중 추천 경로(그늘 최대/균형/최단) — 사용자가 지도에서 선택
- context: 배경 도로망
- hourly: 시간별 위험지수(실측 예보+대기질)
"""
from __future__ import annotations

import json
import os

from engine.risk import walk_advisory
from engine.routing import nearest_node, recommend_routes, route_payload
from engine.sources import osm
from engine.sources.real_graph import build_real_routing_graph
from engine.sources.weather import hourly_risk_series

# 삼전동 → 석촌호수 인근 (아파트 밀집, 그늘 대안 뚜렷 → 3안)
GPS_LATLON = (37.5030, 127.0930)   # 사용자 현재 위치(GPS)
DEST_LATLON = (37.5050, 127.1060)
OUT = "data/demo/map_data.json"

# route_payload / edge_polyline 은 engine.routing.payload 에서 공용화(GPS 서버와 동일 직렬화).


def main():
    G, buildings, trees, env, missing = build_real_routing_graph()
    pois = osm.fetch_pois()
    orig = nearest_node(G, *GPS_LATLON)
    dest = nearest_node(G, *DEST_LATLON)
    opts = recommend_routes(G, orig, dest, pois=pois)
    routes = [route_payload(G, o["route"], o["label"]) for o in opts]

    # bbox: 모든 경로 정점 + 여백
    xs = [p[0] for rt in routes for s in rt["segs"] for p in s["line"]]
    ys = [p[1] for rt in routes for s in rt["segs"] for p in s["line"]]
    pad = 0.003
    bbox = [min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad]

    ctx, seen = [], set()
    for u, v, d in G.edges(data=True):
        key = frozenset((u, v))
        if key in seen:
            continue
        ux, uy = float(G.nodes[u]["x"]), float(G.nodes[u]["y"])
        if not (bbox[0] <= ux <= bbox[2] and bbox[1] <= uy <= bbox[3]):
            continue
        seen.add(key)
        geom = d.get("geometry")
        if geom is not None and hasattr(geom, "coords"):
            ctx.append([[round(x, 6), round(y, 6)] for x, y in geom.coords])
        else:
            ctx.append([[round(ux, 6), round(uy, 6)],
                        [round(float(G.nodes[v]["x"]), 6), round(float(G.nodes[v]["y"]), 6)]])

    hourly = hourly_risk_series(hours=12)
    adv = walk_advisory(env, missing=missing) if env else None
    data = {
        "bbox": bbox,
        "gps": {"lon": GPS_LATLON[1], "lat": GPS_LATLON[0]},
        "origin": [round(float(G.nodes[orig]["x"]), 6), round(float(G.nodes[orig]["y"]), 6)],
        "dest": [round(float(G.nodes[dest]["x"]), 6), round(float(G.nodes[dest]["y"]), 6)],
        "routes": routes,
        "context": ctx,
        "hourly": hourly,
        "meta": {
            "now_score": hourly[0]["score"] if hourly else None,
            "now_level": hourly[0]["level"] if hourly else None,
            "now_dominant": hourly[0]["dominant"] if hourly else None,
            "advisory": adv.status if adv else None,
            "advisory_reason": adv.reason if adv else None,
            "rain": adv.rain if adv else False,
            "air_temp_c": env.air_temp_c if env else None,
            "humidity_pct": env.humidity_pct if env else None,
            "pm10": env.pm10 if env else None,
            "precip_prob_pct": env.precip_prob_pct if env else None,
        },
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    print(f"routes={len(routes)} ({', '.join(r['label']+':'+str(r['shade']) for r in routes)}) "
          f"context={len(ctx)} hourly={len(hourly)}")
    print(f"meta={json.dumps(data['meta'], ensure_ascii=False)}")


if __name__ == "__main__":
    main()
