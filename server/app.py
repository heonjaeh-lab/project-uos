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

logger = logging.getLogger("pawtrail.server")

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from engine.sources.local_routing import gps_map_payload

app = FastAPI(title="조심해야댕 GPS 라우팅 API", version="1.0")

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
    dest = (dest_lat, dest_lon) if dest_lat is not None and dest_lon is not None else None
    try:
        payload = gps_map_payload(lat, lon, dest=dest)
    except Exception:  # 엔진/외부 API 실패 → 502(프론트가 데모 폴백)
        logger.exception("route build failed (lat=%s lon=%s)", lat, lon)  # 실오류는 서버 로그로만
        raise HTTPException(status_code=502, detail="route build failed")  # 키 유출 방지: 예외 문자열 미노출
    if not payload.get("routes"):
        raise HTTPException(status_code=404, detail="no route found near location")
    return JSONResponse(payload)
