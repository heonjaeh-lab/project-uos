"""데모: 서울 어디서든 GPS 기준 로컬 라우팅 (engine.sources.local_routing).

전 지역을 들지 않고 GPS 주변만 온디맨드(타일 캐시)로 처리한다.
실행: PYTHONPATH=. .venv/bin/python scripts/poc_gps_anywhere.py [lat lon]
"""
from __future__ import annotations

import sys
import time

from engine.sources.local_routing import route_from_gps

# 기본: 강남역(비-송파). 인자로 임의 좌표 지정 가능.
GPS = (float(sys.argv[1]), float(sys.argv[2])) if len(sys.argv) >= 3 else (37.4979, 127.0276)
DEST = (GPS[0] + 0.008, GPS[1] + 0.010)  # 북동 ~1.2km


def main():
    t0 = time.time()
    opts = route_from_gps(GPS[0], GPS[1], dest=DEST)
    print(f"GPS {GPS} → 목적지 {DEST}: 추천 {len(opts)}안 · {time.time() - t0:.1f}s")
    for o in opts:
        r = o["route"]
        print(f"  [{o['label']}] 그늘 {r.avg_shade_ratio:.2f} · {r.distance_m:.0f}m · "
              f"{r.est_time_min:.0f}분 · 경유 안전지점 {len(r.pois_on_route)}")
    if not opts:
        print("  (경로 없음 — 해당 위치 데이터/네트워크 확인)")


if __name__ == "__main__":
    main()
