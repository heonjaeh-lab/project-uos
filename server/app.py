"""조심해야댕 GPS 라우팅 API — 정적 앱(GitHub Pages)이 HTTPS로 호출하는 얇은 FastAPI 래퍼.

GET /api/health → {"status":"ok"}
GET /api/route?lat&lon[&dest_lat&dest_lon]
    → engine.sources.local_routing.gps_map_payload(...) (map_data.json 동일 스키마).

엔진 계산은 블로킹(OSM 다운로드·shapely·외부 API)이라 sync 핸들러로 두면 FastAPI가
스레드풀에서 실행한다. 런타임 LLM 없음 · 결정론 유지.
"""
from __future__ import annotations

import os
import logging
import threading

logger = logging.getLogger("pawtrail.server")

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from engine.sources.local_routing import gps_map_payload, _haversine_m

app = FastAPI(title="조심해야댕 GPS 라우팅 API", version="1.0")

# 서비스 지오펜스 — 한국 육상 대략 bbox. 밖 좌표는 즉시 거절해 무의미한 OSM/외부 API 호출·
# 캐시 파일 증식(좌표 열거 남용)을 막는다. dest는 도보 가능 거리로 상한을 둬 그래프 반경이
# 무한정 커지는 것(원거리 목적지 → OOM/장시간 행)을 방지한다.
_KR_LAT = (33.0, 39.0)
_KR_LON = (124.0, 132.0)
_MAX_DEST_M = 8000.0

# 무거운 엔진 연산(OSM 다운로드·shapely·외부 API)의 동시 실행 상한. 1cpu/2Gi 컨테이너에서
# 다수 동시 요청이 그래프를 동시에 메모리에 올려 OOM 나는 것을 막는다. 초과 요청은 503(빠른 실패).
# health는 세마포어 밖이라 포화 중에도 응답 유지. 값은 MAX_CONCURRENT_ROUTES 로 조정.
_route_sem = threading.BoundedSemaphore(int(os.environ.get("MAX_CONCURRENT_ROUTES", "3")))


def _in_korea(lat: float, lon: float) -> bool:
    return _KR_LAT[0] <= lat <= _KR_LAT[1] and _KR_LON[0] <= lon <= _KR_LON[1]

# CORS: 기본 전체 허용(공개 read-only GET). ALLOW_ORIGINS(쉼표구분)로 제한 가능.
_origins = os.environ.get("ALLOW_ORIGINS", "*").strip()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if _origins == "*" else [o.strip() for o in _origins.split(",")],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/route")
def route(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    dest_lat: float | None = Query(None, ge=-90, le=90),
    dest_lon: float | None = Query(None, ge=-180, le=180),
) -> JSONResponse:
    # 지오펜스: 서비스 지역(한국) 밖이면 엔진에 넘기지 않고 즉시 거절.
    if not _in_korea(lat, lon):
        raise HTTPException(status_code=422, detail="location outside service area (Korea only)")
    dest = (dest_lat, dest_lon) if dest_lat is not None and dest_lon is not None else None
    if dest is not None:
        if not _in_korea(dest[0], dest[1]):
            raise HTTPException(status_code=422, detail="destination outside service area (Korea only)")
        if _haversine_m(lat, lon, dest[0], dest[1]) > _MAX_DEST_M:
            raise HTTPException(status_code=422,
                                detail=f"destination too far (walking route ≤ {int(_MAX_DEST_M)}m)")

    # 동시 실행 상한 초과 → 즉시 503(스레드/메모리 점유 폭주 방지). 검증 실패는 세마포어 전에 처리.
    if not _route_sem.acquire(blocking=False):
        raise HTTPException(status_code=503, detail="server busy, please retry shortly")
    try:
        # GPS 앱 프로파일: ~1.5km 루프(그래프 반경↓ → 콜드 응답 빠르게). 근거: 계획 T6 성능 측정.
        payload = gps_map_payload(lat, lon, dest=dest, dist_m=1000, target_m=1500)
    except Exception:  # 엔진/외부 API 실패 → 502(프론트가 데모 폴백)
        logger.exception("route build failed (lat=%s lon=%s)", lat, lon)  # 실오류는 서버 로그로만
        raise HTTPException(status_code=502, detail="route build failed")  # 키 유출 방지: 예외 문자열 미노출
    finally:
        _route_sem.release()
    if not payload.get("routes"):
        raise HTTPException(status_code=404, detail="no route found near location")
    return JSONResponse(payload)
