# GPS 라이브 라우팅(Azure Container Apps) 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** GitHub Pages 정적 앱이 사용자 GPS 좌표를 Azure의 FastAPI 서버로 보내 서울 어디서든 실데이터 산책 경로를 받아 렌더하도록 Phase 2를 완성한다.

**Architecture:** 정적 앱(Leaflet)은 항상 데모 경로를 렌더하고, "안전한 길 찾기"만 브라우저 Geolocation → `GET /api/route?lat&lon` (Azure, HTTPS) → 엔진 `gps_map_payload()`가 `map_data.json`과 **동일 스키마** dict 반환 → 프론트가 `DATA`를 교체해 재렌더. API 장애/권한 거부 시 데모로 폴백해 앱이 안 깨진다. 로컬 docker가 없어 이미지는 `az acr build`로 클라우드 빌드한다.

**Tech Stack:** Python 3.13 · FastAPI + uvicorn · 기존 엔진(osmnx/shapely/pyproj/astral/networkx/pydantic) · Leaflet(프론트) · Azure Container Apps(min replicas=1, external HTTPS ingress) · Azure Container Registry(`az acr build`).

## Global Constraints

- 언어 Python · 런타임 LLM 금지 · 결정론 유지(스펙 `docs/superpowers/specs/2026-07-08-leaflet-map-azure-gps-design.md`).
- API 키는 코드/이미지에 굽지 않음 — 로컬은 `.env`(gitignore), Azure는 컨테이너 시크릿(env 주입). 엔진 키 로딩은 `engine/sources/config.py`(우선순위: 실제 환경변수 > `.env`).
- 좌표는 `[lon, lat]`(GeoJSON 순서)·소수점 6자리 — `engine/routing/payload.py` 규약을 따른다.
- 엔진 실행: `.venv/bin/python`, 테스트: `.venv/bin/python -m pytest`.
- 리포: `github.com/heonjaeh-lab/project-uos` · Pages 오리진 `https://heonjaeh-lab.github.io`.
- 버전 고정(서버 requirements): 기존 `requirements.txt` 핀 집합 + `requests`(엔진이 사용, 현재 osmnx 경유로만 설치됨) + `fastapi`/`uvicorn`/`httpx`.

## 현재 상태(시작점)

- ✅ 커밋됨: Leaflet 렌더(`aeec022`), 엔진 `route_from_gps()`.
- 🟡 커밋 안 됨(작성됐으나 **한 번도 실행 안 됨**): `engine/routing/payload.py`(신규), `local_routing.gps_map_payload()`, `weather.hourly_risk_series(lat, lon)` 격자 일반화, `export_map_data.py` 리팩터, `engine/routing/__init__.py` export.
- ❌ 없음: `server/`, `requirements-server.txt`, 프론트 GPS 배관, Azure 배포.

이 계획은 🟡을 테스트로 고정→커밋하고 ❌를 만든다.

---

### Task 1: 공용 직렬화 모듈(`engine/routing/payload.py`) 테스트로 고정 + 커밋

이미 작성된(미커밋) `payload.py`의 3함수를 순수 단위 테스트로 고정한다. 네트워크 없음.

**Files:**
- Test: `tests/test_payload.py` (create)
- Commit: `engine/routing/payload.py`, `engine/routing/__init__.py`, `scripts/export_map_data.py`(이미 리팩터됨)

**Interfaces:**
- Consumes: `engine.routing.payload.edge_polyline(G,u,v) -> (list[[lon,lat]], float)`, `route_payload(G, r: RouteResult, label) -> dict`, `routes_bbox(routes, *, center=None, pad=0.003) -> [minlon,minlat,maxlon,maxlat]`
- Produces: (없음 — 계약 고정만)

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_payload.py`

```python
"""engine.routing.payload — 프론트 map_data 스키마 직렬화(순수, 네트워크 없음)."""
from __future__ import annotations

import networkx as nx
import pytest

from engine.routing.payload import edge_polyline, route_payload, routes_bbox
from engine.schemas import RiskLevel
from engine.schemas.poi import POI, POIType
from engine.schemas.route import RouteResult


def _toy_graph() -> nx.MultiDiGraph:
    # A(1)→C(3)→B(2). geometry 없음 → 노드 좌표로 폴백. shade_ratio·cost 부여.
    G = nx.MultiDiGraph()
    G.add_node(1, x=127.100, y=37.500)
    G.add_node(2, x=127.102, y=37.500)
    G.add_node(3, x=127.101, y=37.501)
    for a, b, sh in ((1, 3, 0.8), (3, 2, 0.4)):
        for u, v in ((a, b), (b, a)):
            G.add_edge(u, v, length=70.0, shade_ratio=sh, cost=70.0)
    return G


def test_edge_polyline_falls_back_to_node_coords():
    G = _toy_graph()
    line, shade = edge_polyline(G, 1, 3)
    assert line == [[127.1, 37.5], [127.101, 37.501]]   # [lon,lat]
    assert shade == 0.8


def test_route_payload_shape():
    G = _toy_graph()
    r = RouteResult(
        node_path=[1, 3, 2], distance_m=140.0, est_time_min=1.9,
        avg_shade_ratio=0.6, max_risk_level=RiskLevel.green,
        pois_on_route=[POI(poi_type=POIType.water_fountain, lat=37.5005,
                           lon=127.1005, name="급수대")],
    )
    p = route_payload(G, r, "동네 순환")
    assert p["label"] == "동네 순환"
    assert p["shade"] == 0.6 and p["distance_m"] == 140 and p["max_risk"] == "green"
    assert len(p["segs"]) == 2
    assert p["segs"][0]["line"] == [[127.1, 37.5], [127.101, 37.501]]
    assert p["pois"][0] == {"lon": 127.1005, "lat": 37.5005,
                            "type": "water_fountain", "name": "급수대"}


def test_routes_bbox_covers_all_points_with_pad():
    G = _toy_graph()
    r = RouteResult(node_path=[1, 3, 2], max_risk_level=RiskLevel.green)
    routes = [route_payload(G, r, "x")]
    bb = routes_bbox(routes, pad=0.001)
    assert bb == pytest.approx([127.099, 37.499, 127.103, 37.502])   # min-pad .. max+pad (float)


def test_routes_bbox_empty_uses_center():
    bb = routes_bbox([], center=(37.5, 127.0))
    assert bb == pytest.approx([126.99, 37.49, 127.01, 37.51])
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_payload.py -q`
Expected: 이미 impl이 있으므로 **PASS** 가능. FAIL이면 impl 계약과 테스트 기대를 대조해 테스트를 실제 반환값에 맞춘다(값 오타 수정). PASS면 다음 단계로.

- [ ] **Step 3: 전체 회귀 확인**

Run: `.venv/bin/python -m pytest -q`
Expected: 기존 테스트 전부 PASS(리팩터가 export만 건드림). FAIL 나는 기존 테스트가 있으면 `export_map_data`의 `route_payload` import 경로를 점검.

- [ ] **Step 4: 커밋**

```bash
git add engine/routing/payload.py engine/routing/__init__.py scripts/export_map_data.py tests/test_payload.py
git commit -m "refactor(routing): map_data 직렬화 공용화(payload) + 단위 테스트

$(printf 'Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 2: `gps_map_payload` 실행 검증(라이브 스모크) + `hourly_risk_series` 격자 단위 테스트 + 커밋

`gps_map_payload`는 외부 API·OSM 다운로드를 타서 순수 단위 테스트가 어렵다. (a) `hourly_risk_series`의 격자 선택은 fetch를 monkeypatch해 결정론 검증하고, (b) `gps_map_payload`는 실좌표로 **한 번 실제 실행**해 스키마를 확인한다(네트워크 게이트).

**Files:**
- Test: `tests/test_gps_payload.py` (create)
- Commit: `engine/sources/local_routing.py`, `engine/sources/weather.py`, 새 테스트

**Interfaces:**
- Consumes: `engine.sources.weather.hourly_risk_series(when=None, hours=12, params=None, lat=None, lon=None) -> list[dict]`, `engine.sources.local_routing.gps_map_payload(lat, lon, dest=None, *, dist_m=1800, target_m=2000, when=None, pois=None, cost_params=None, hours=12) -> dict`
- Produces: `gps_map_payload` 반환 dict 키 = `{bbox, gps, origin, dest, routes, hourly, meta}` (프론트·서버가 의존)

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_gps_payload.py`

```python
"""GPS payload — 격자 선택(단위) + 실좌표 스키마(네트워크 게이트)."""
from __future__ import annotations

import os

import pytest

from engine.sources import weather


def test_hourly_risk_series_uses_gps_grid(monkeypatch):
    """lat/lon 지정 시 해당 격자(nx,ny)로 예보를 요청해야 한다(송파 기본 아님)."""
    captured = {}

    def fake_series(nx, ny, when=None, hours=12):
        captured["grid"] = (nx, ny)
        return []  # 시리즈 비면 out=[] → 격자 캡처만 검증

    monkeypatch.setattr(weather, "fetch_forecast_series", fake_series)
    monkeypatch.setattr(weather, "fetch_air_quality", lambda: {"pm10": 20.0, "pm25": 10.0})

    # 광화문 근처(송파와 다른 격자)
    weather.hourly_risk_series(hours=6, lat=37.5759, lon=126.9769)
    seoul_center_grid = weather.latlon_to_grid(37.5759, 126.9769)
    assert captured["grid"] == seoul_center_grid
    assert captured["grid"] != (weather.SONGPA_NX, weather.SONGPA_NY)


@pytest.mark.skipif(os.environ.get("RUN_LIVE") != "1",
                    reason="네트워크 라이브 스모크 — RUN_LIVE=1 일 때만")
def test_gps_map_payload_live_schema():
    """실좌표(서울시청 근처)로 실제 payload 생성 — map_data 스키마 키 검증."""
    from engine.sources.local_routing import gps_map_payload
    p = gps_map_payload(37.5663, 126.9779, dist_m=1200, target_m=1400, hours=6)
    for k in ("bbox", "gps", "origin", "dest", "routes", "hourly", "meta"):
        assert k in p, f"missing key {k}"
    assert len(p["bbox"]) == 4
    for rt in p["routes"]:
        assert {"label", "shade", "distance_m", "est_time_min", "max_risk", "segs", "pois"} <= rt.keys()
```

- [ ] **Step 2: 격자 단위 테스트 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_gps_payload.py::test_hourly_risk_series_uses_gps_grid -v`
Expected: PASS(diff의 lat/lon 분기가 이미 구현됨). FAIL이면 `hourly_risk_series` 시그니처/분기 확인.

- [ ] **Step 3: 라이브 스모크 실제 실행(핵심 — 한 번도 안 돌린 코드 검증)**

Run: `RUN_LIVE=1 .venv/bin/python -m pytest tests/test_gps_payload.py::test_gps_map_payload_live_schema -v -s`
Expected: PASS (콜드 시 20~40s 소요 — OSM 다운로드+V-World+기상). 실패 시 systematic-debugging: 에러 트레이스로 `build_local_graph`/`build_env_at`/`route_payload` 경계 확인. `.env` 키 존재 필요.

- [ ] **Step 4: 회귀 + 커밋**

```bash
.venv/bin/python -m pytest -q
git add engine/sources/local_routing.py engine/sources/weather.py tests/test_gps_payload.py
git commit -m "feat(engine): gps_map_payload(서울 임의좌표→map_data 스키마) + 시간별 위험 격자 일반화

$(printf 'Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 3: FastAPI 서버(`server/app.py`) + `requirements-server.txt` + 단위 테스트

**Files:**
- Create: `server/__init__.py`, `server/app.py`, `requirements-server.txt`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: `engine.sources.local_routing.gps_map_payload`
- Produces: ASGI 앱 `server.app:app` · `GET /api/health` → `{"status":"ok"}` · `GET /api/route?lat&lon[&dest_lat&dest_lon]` → payload dict(200) / 404(경로없음) / 422(파라미터오류) / 502(엔진실패)

- [ ] **Step 1: 서버 실행 의존성 설치(.venv)**

Run: `.venv/bin/pip install "fastapi==0.115.6" "uvicorn[standard]==0.34.0" "httpx==0.28.1"`
Expected: 설치 성공(테스트·로컬 실행용).

- [ ] **Step 2: `requirements-server.txt` 작성** (create)

```
# 조심해야댕 GPS 라우팅 서버 — 엔진 런타임 + FastAPI. pytest 등 개발도구 제외.
osmnx==2.1.0
shapely==2.1.2
pyproj==3.7.2
astral==3.2
networkx==3.6.1
numpy==2.5.1
pandas==3.0.3
pydantic==2.13.4
geojson==3.3.0
requests==2.32.3
fastapi==0.115.6
uvicorn[standard]==0.34.0
httpx==0.28.1
```

- [ ] **Step 3: `server/__init__.py` 작성** (create)

```python
"""조심해야댕 GPS 라우팅 서버 패키지."""
```

- [ ] **Step 4: 실패 테스트 작성** — `tests/test_server.py`

```python
"""FastAPI GPS 라우팅 서버 — 핸들러 계약(엔진은 monkeypatch, 네트워크 없음)."""
from __future__ import annotations

from fastapi.testclient import TestClient

import server.app as srv

client = TestClient(srv.app)

_FAKE = {
    "bbox": [127.0, 37.5, 127.01, 37.51], "gps": {"lon": 127.0, "lat": 37.5},
    "origin": [127.0, 37.5], "dest": [127.01, 37.51],
    "routes": [{"label": "동네 순환", "shade": 0.5, "distance_m": 1800,
                "est_time_min": 24.0, "max_risk": "green", "segs": [], "pois": []}],
    "hourly": [], "meta": {"advisory": "go"},
}


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_route_ok(monkeypatch):
    monkeypatch.setattr(srv, "gps_map_payload", lambda *a, **k: _FAKE)
    r = client.get("/api/route?lat=37.5&lon=127.0")
    assert r.status_code == 200
    assert r.json()["routes"][0]["label"] == "동네 순환"


def test_route_passes_dest(monkeypatch):
    seen = {}
    def spy(lat, lon, dest=None, **k):
        seen["dest"] = dest
        return _FAKE
    monkeypatch.setattr(srv, "gps_map_payload", spy)
    client.get("/api/route?lat=37.5&lon=127.0&dest_lat=37.51&dest_lon=127.02")
    assert seen["dest"] == (37.51, 127.02)


def test_route_no_route_404(monkeypatch):
    monkeypatch.setattr(srv, "gps_map_payload", lambda *a, **k: {"routes": []})
    assert client.get("/api/route?lat=37.5&lon=127.0").status_code == 404


def test_route_engine_error_502(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("osm down")
    monkeypatch.setattr(srv, "gps_map_payload", boom)
    assert client.get("/api/route?lat=37.5&lon=127.0").status_code == 502


def test_route_bad_param_422():
    assert client.get("/api/route?lat=999&lon=127").status_code == 422
```

- [ ] **Step 5: 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_server.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'server.app'`.

- [ ] **Step 6: `server/app.py` 작성** (create)

```python
"""조심해야댕 GPS 라우팅 API — 정적 앱(GitHub Pages)이 HTTPS로 호출하는 얇은 FastAPI 래퍼.

GET /api/health → {"status":"ok"}
GET /api/route?lat&lon[&dest_lat&dest_lon]
    → engine.sources.local_routing.gps_map_payload(...) (map_data.json 동일 스키마).

엔진 계산은 블로킹(OSM 다운로드·shapely·외부 API)이라 sync 핸들러로 두면 FastAPI가
스레드풀에서 실행한다. 런타임 LLM 없음 · 결정론 유지.
"""
from __future__ import annotations

import os

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
    except Exception as e:  # 엔진/외부 API 실패 → 502(프론트가 데모 폴백)
        raise HTTPException(status_code=502, detail=f"route build failed: {e}")
    if not payload.get("routes"):
        raise HTTPException(status_code=404, detail="no route found near location")
    return JSONResponse(payload)
```

- [ ] **Step 7: 통과 확인**

Run: `.venv/bin/python -m pytest tests/test_server.py -q`
Expected: 6 passed.

- [ ] **Step 8: 커밋**

```bash
git add server/__init__.py server/app.py requirements-server.txt tests/test_server.py
git commit -m "feat(server): FastAPI GPS 라우팅 API(/api/route,/api/health)+CORS+테스트

$(printf 'Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 4: `server/Dockerfile` + `.dockerignore`(빌드 컨텍스트 축소)

로컬 docker가 없어 `az acr build`(Task 7)에서 처음 빌드된다. 여기선 파일 작성 + requirements 설치 가능성 로컬 검증.

**Files:**
- Create: `server/Dockerfile`, `.dockerignore`(리포 루트 — 빌드 컨텍스트가 루트)

- [ ] **Step 1: `.dockerignore` 작성** (리포 루트, create) — `.venv`·`data/cache`(대용량 graphml)·`.git`·`docs`를 업로드에서 제외

```
.venv
.git
__pycache__
*.pyc
data/cache
data/demo
cache
docs
tests
_workspace
*.jpeg
*.pdf
.env
.playwright-mcp
```

- [ ] **Step 2: `server/Dockerfile` 작성** (create)

```dockerfile
# 조심해야댕 GPS 라우팅 — python:3.13-slim. shapely/pyproj/geopandas는 manylinux wheel로 설치되어
# 시스템 geos/proj 없이도 import 된다(대개). wheel 누락으로 빌드 실패 시 Task 7 폴백 참고.
FROM python:3.13-slim

WORKDIR /app

COPY requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt

COPY engine ./engine
COPY server ./server

ENV PYTHONUNBUFFERED=1 PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn server.app:app --host 0.0.0.0 --port ${PORT}"]
```

- [ ] **Step 3: requirements 설치 가능성 로컬 검증(핀 집합 해결 확인)**

Run: `.venv/bin/python -m pip install --dry-run -r requirements-server.txt`
Expected: 의존성 해결 성공(충돌 없음). 충돌 시 핀을 `.venv` 실제 설치버전에 맞춘다: `.venv/bin/pip freeze | grep -iE 'osmnx|shapely|pyproj|astral|networkx|numpy|pandas|pydantic|geojson|requests'`.

- [ ] **Step 4: 커밋**

```bash
git add server/Dockerfile .dockerignore
git commit -m "feat(server): Dockerfile(python3.13-slim)+.dockerignore(빌드 컨텍스트 축소)

$(printf 'Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 5: 프론트 GPS 배관(`scripts/make_app.py`) + 앱 재생성 + 브라우저 검증

앱에 `API_BASE`·Geolocation·fetch·로딩/토스트/폴백을 추가한다. `API_BASE=""`(기본)면 데모만; 값이 있으면 GPS→서버.

**Files:**
- Modify: `scripts/make_app.py`
- Regenerate: `docs/app/조심해야댕.html`, `docs/app/index.html`

**Interfaces:**
- Consumes: 서버 `GET /api/route?lat&lon`(Task 3)
- Produces: JS 전역 `findRoute()`(홈 CTA·경로 화면 "다시" 버튼이 호출), `const API_BASE`

- [ ] **Step 1: `make_app.py` 상단에 API_BASE 파이썬 상수 추가**

`scripts/make_app.py`의 `SRC`/`OUT` 정의 직후에 삽입:
```python
import os
API_BASE = os.environ.get("API_BASE", "")   # 빌드시 주입: 로컬 http://localhost:8000 / prod Azure FQDN
```

- [ ] **Step 2: 경로 화면 GPS 헤더에 "다시 찾기" 버튼 추가**

`make_app.py`에서 아래 줄(경로 화면, 현재 line ~184)을 교체:
```html
      <div style="font-weight:700;font-size:12px;color:#9A928B;margin-bottom:8px">📍 내 위치(GPS)에서 · 추천 3개 중 골라</div>
```
→
```html
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
        <span style="font-weight:700;font-size:12px;color:#9A928B;flex:1">📍 내 위치(GPS)에서 · 추천 3개 중 골라</span>
        <button onclick="findRoute()" style="border:1.5px solid #F1592A;background:#FDEDE4;color:#C24E24;font-family:'Gothic A1';font-weight:800;font-size:11.5px;border-radius:999px;padding:5px 11px;cursor:pointer">📍 다시</button>
      </div>
```

- [ ] **Step 3: GPS 로딩 오버레이 + 토스트 요소 추가**

`make_app.py`에서 하단 탭바 닫는 `</div>` 다음, `.phone` 닫는 `</div>`(현재 line ~317) **직전**에 삽입:
```html
  <!-- GPS 로딩 / 토스트 -->
  <div class="maploading" id="gpsLoading" style="border-radius:44px">
    <div class="spin"></div>
    <div id="gpsLoadingMsg">내 위치에서 안전한 길을 찾는 중…<br><span style="font-size:11px;color:#B9AE9F">동네 지도를 처음 받는 중이면 조금 걸려요</span></div>
  </div>
  <div id="toast" style="position:absolute;left:16px;right:16px;top:54px;z-index:1300;display:none;background:#2E2A27;color:#fff;font-weight:700;font-size:12.5px;padding:11px 14px;border-radius:14px;box-shadow:0 8px 20px rgba(46,42,39,.3);text-align:center;animation:toastin .3s ease"></div>
```

- [ ] **Step 4: GPS JS 로직 추가**

`make_app.py`의 `<script>` 안, `const DATA=__DATA__;` 다음 줄에 삽입:
```javascript
const API_BASE="__API_BASE__";   // "" → 데모만. 값 있으면 GPS→서버 호출.
```
그리고 `go('home');`(스크립트 끝, 현재 line ~502) **직전**에 삽입:
```javascript
// ---- GPS 라이브 라우팅 (Azure API) ----
function showGpsLoading(on,msg){const el=$('gpsLoading');
  if(msg)$('gpsLoadingMsg').innerHTML=msg;el.classList.toggle('on',on);}
let toastT=null;
function toast(msg){const t=$('toast');t.textContent=msg;t.style.display='block';
  clearTimeout(toastT);toastT=setTimeout(()=>t.style.display='none',3200);}
function findRoute(){
  if(!API_BASE||!navigator.geolocation){go('route');return;}       // 폴백: 데모 경로
  showGpsLoading(true);
  navigator.geolocation.getCurrentPosition(
    p=>fetchRoute(p.coords.latitude,p.coords.longitude),
    ()=>{showGpsLoading(false);toast('위치를 못 받아 데모 경로를 보여줘요');go('route');},
    {enableHighAccuracy:true,timeout:15000,maximumAge:60000});
}
async function fetchRoute(lat,lon){
  const ctrl=new AbortController();const timer=setTimeout(()=>ctrl.abort(),45000);  // 콜드 대비
  try{
    const res=await fetch(`${API_BASE}/api/route?lat=${lat}&lon=${lon}`,{signal:ctrl.signal});
    if(!res.ok)throw new Error('http '+res.status);
    const data=await res.json();
    if(!data.routes||!data.routes.length)throw new Error('no routes');
    for(const k of Object.keys(DATA))delete DATA[k];Object.assign(DATA,data);        // DATA 교체(const 유지)
    sel=0;showGpsLoading(false);go('route');
  }catch(e){showGpsLoading(false);
    toast('경로 서버 응답이 없어 데모 경로를 보여줘요');go('route');
  }finally{clearTimeout(timer);}
}
```

- [ ] **Step 5: 홈 CTA를 findRoute로 연결**

`make_app.py` `renderHome()` 안(현재 line ~426):
```javascript
  else{cta.classList.remove('disabled');cta.textContent='안전한 길 찾기';cta.onclick=()=>go('route');}
```
→
```javascript
  else{cta.classList.remove('disabled');cta.textContent='안전한 길 찾기';cta.onclick=()=>findRoute();}
```

- [ ] **Step 6: `__API_BASE__` 치환 추가**

`make_app.py` 마지막 렌더(현재 line ~507):
```python
out = HTML.replace("__DATA__", json.dumps(DATA, ensure_ascii=False))
```
→
```python
out = HTML.replace("__DATA__", json.dumps(DATA, ensure_ascii=False)).replace("__API_BASE__", API_BASE)
```

- [ ] **Step 7: 앱 재생성(데모 모드 — API_BASE 미설정)**

Run: `.venv/bin/python scripts/make_app.py`
Expected: `wrote docs/app/조심해야댕.html + index.html (...bytes)`. 생성물에 `const API_BASE="";`가 들어가야 함 → `grep -c 'const API_BASE=""' docs/app/index.html` == 1.

- [ ] **Step 8: 브라우저 검증(geolocation·fetch 스텁)**

로컬 정적 서버로 앱을 띄운 뒤(권한/CORS 회피 위해 http):
```bash
cd docs/app && ../../.venv/bin/python -m http.server 8080 &
```
Playwright MCP로 `http://localhost:8080/index.html` 열기 → `browser_evaluate`로 스텁 주입 후 CTA 클릭:
```javascript
() => {
  window.__API = "http://x";                    // API_BASE 빈 값이어도 findRoute 진입 위해
  navigator.geolocation.getCurrentPosition = (ok) => ok({coords:{latitude:37.5663,longitude:126.9779}});
  window.fetch = async () => ({ok:true, json: async () => ({
    bbox:[126.97,37.56,126.99,37.58], gps:{lon:126.9779,lat:37.5663},
    origin:[126.9779,37.5663], dest:[126.98,37.57],
    routes:[{label:"스텁 경로", shade:0.7, distance_m:1500, est_time_min:20,
      max_risk:"green", segs:[{line:[[126.9779,37.5663],[126.98,37.57]], shade:0.7}], pois:[]}],
    hourly:[], meta:{advisory:"go"}
  })});
}
```
> 주의: 생성된 앱의 `API_BASE`가 `""`면 `findRoute`가 바로 `go('route')`로 폴백한다. 이 스텁 검증은 `API_BASE`가 설정된 빌드에서 의미가 있으므로, 검증용으로 `API_BASE=http://localhost:8080 .venv/bin/python scripts/make_app.py`로 한 번 생성해 연 뒤 위 스텁으로 클릭 → 경로 화면에 "스텁 경로" 칩이 보이는지 확인. 확인 후 **데모 모드로 재생성**(Step 7)해 커밋.

Expected: 경로 화면 `#rchips`에 "스텁 경로" 노출 + `#routeMap` 렌더.

- [ ] **Step 9: 커밋(데모 모드 산출물)**

```bash
git add scripts/make_app.py docs/app/index.html "docs/app/조심해야댕.html"
git commit -m "feat(app): GPS 배관(Geolocation→/api/route→렌더)+로딩·데모 폴백

$(printf 'Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

### Task 6: 로컬 E2E 게이트(uvicorn 로컬 + 실 fetch)

Azure 전, 엔진→서버→프론트가 **실제로** 동작하는지 로컬에서 확인. geolocation만 스텁, fetch는 실제 로컬 서버.

- [ ] **Step 1: 로컬 서버 기동**

Run(백그라운드): `.venv/bin/uvicorn server.app:app --host 127.0.0.1 --port 8000`
확인: `curl -s http://127.0.0.1:8000/api/health` → `{"status":"ok"}`

- [ ] **Step 2: 실 라우트 스모크(콜드 감내)**

Run: `curl -s "http://127.0.0.1:8000/api/route?lat=37.5663&lon=126.9779" | .venv/bin/python -m json.tool | head -40`
Expected: `routes`·`bbox`·`meta` 포함 JSON(20~40s). 실패 시 서버 로그 확인 후 systematic-debugging.

- [ ] **Step 3: 앱을 localhost API로 빌드 + 정적 서빙**

```bash
API_BASE="http://localhost:8000" .venv/bin/python scripts/make_app.py
cd docs/app && ../../.venv/bin/python -m http.server 8080 &
```

- [ ] **Step 4: Playwright E2E — 실 GPS 흐름**

`http://localhost:8080/index.html` 열기 → `browser_evaluate`로 geolocation만 스텁(서울시청):
```javascript
() => { navigator.geolocation.getCurrentPosition = (ok) =>
  ok({coords:{latitude:37.5663, longitude:126.9779}}); }
```
→ 홈 "안전한 길 찾기" 클릭 → 로딩 오버레이(`#gpsLoading.on`) 표시 확인 → 최대 45s 대기(`browser_wait_for` 경로 화면 텍스트) → `#rchips`에 실 경로 칩·`#routeMap` 렌더 확인. `browser_console_messages`로 에러 없음 확인.
Expected: 실좌표 경로가 지도에 렌더. **이 게이트 통과가 Azure 진행 조건.**

- [ ] **Step 5: 정리 + 데모 모드 재빌드**

로컬 서버·http.server 종료. `.venv/bin/python scripts/make_app.py`(API_BASE 미설정)로 데모 모드 복구(아직 커밋 안 함 — Task 7에서 FQDN으로 최종 빌드).

---

### Task 7: Azure Container Apps 배포 + 프론트 FQDN 연결

`az` 로그인됨(Azure for Students). 로컬 docker 없음 → `az acr build`.

- [ ] **Step 1: 확장·프로바이더 준비**

```bash
az extension add --name containerapp --upgrade -y
az provider register --namespace Microsoft.App --wait
az provider register --namespace Microsoft.OperationalInsights --wait
```

- [ ] **Step 2: 리소스 그룹 + ACR**

```bash
RG=pawtrail-rg; LOC=koreacentral; ACR=pawtrailacr$RANDOM; APP=pawtrail-api; ENVN=pawtrail-env
echo "ACR=$ACR"   # 기록해둘 것(전역 유일)
az group create -n $RG -l $LOC
az acr create -n $ACR -g $RG --sku Basic --admin-enabled true
```

- [ ] **Step 3: 클라우드 이미지 빌드(로컬 docker 불필요)**

Run: `az acr build --registry $ACR --image pawtrail-api:v1 --file server/Dockerfile .`
Expected: 빌드 성공.
> 폴백: geos/proj wheel 문제로 실패 시 `server/Dockerfile`의 pip 단계 앞에 아래를 추가하고 재빌드:
> ```dockerfile
> RUN apt-get update && apt-get install -y --no-install-recommends libgeos-dev libproj-dev proj-data && rm -rf /var/lib/apt/lists/*
> ```

- [ ] **Step 4: Container Apps 환경 + 앱(시크릿 주입)**

```bash
az containerapp env create -n $ENVN -g $RG -l $LOC

ACR_SERVER=$(az acr show -n $ACR -g $RG --query loginServer -o tsv)
ACR_USER=$(az acr credential show -n $ACR --query username -o tsv)
ACR_PASS=$(az acr credential show -n $ACR --query 'passwords[0].value' -o tsv)

set -a; source .env; set +a   # 키 6개를 셸 변수로(에코 금지)

az containerapp create -n $APP -g $RG --environment $ENVN \
  --image $ACR_SERVER/pawtrail-api:v1 \
  --registry-server $ACR_SERVER --registry-username $ACR_USER --registry-password "$ACR_PASS" \
  --target-port 8000 --ingress external \
  --min-replicas 1 --max-replicas 1 --cpu 1.0 --memory 2.0Gi \
  --secrets datagokr="$DATA_GO_KR_KEY" kma="$KMA_APIHUB_KEY" seoul="$SEOUL_OPEN_DATA_KEY" \
            vworld="$VWORLD_KEY" vworlddomain="$VWORLD_DOMAIN" \
  --env-vars DATA_GO_KR_KEY=secretref:datagokr KMA_APIHUB_KEY=secretref:kma \
             SEOUL_OPEN_DATA_KEY=secretref:seoul VWORLD_KEY=secretref:vworld \
             VWORLD_DOMAIN=secretref:vworlddomain ALLOW_ORIGINS='*'
```

- [ ] **Step 5: FQDN 확보 + 라이브 스모크**

```bash
FQDN=$(az containerapp show -n $APP -g $RG --query properties.configuration.ingress.fqdn -o tsv)
echo "https://$FQDN"
curl -s "https://$FQDN/api/health"
curl -s "https://$FQDN/api/route?lat=37.5663&lon=126.9779" | .venv/bin/python -m json.tool | head -30
```
Expected: health `ok`, route JSON(콜드 첫 호출 지연). 실패 시 `az containerapp logs show -n $APP -g $RG --tail 100`.
> V-World가 등록 도메인 외 호출을 거부하면(그늘 저하/에러) V-World 콘솔에 `*.azurecontainerapps.io` 또는 FQDN 추가.

- [ ] **Step 6: 프론트를 FQDN으로 빌드 + 배포**

```bash
API_BASE="https://$FQDN" .venv/bin/python scripts/make_app.py
git add scripts/make_app.py docs/app/index.html "docs/app/조심해야댕.html"
git commit -m "feat(app): GPS 라이브 라우팅 Azure FQDN 연결

$(printf 'Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
git push origin main
```

- [ ] **Step 7: 배포 앱 라이브 검증**

GitHub Pages URL(`https://heonjaeh-lab.github.io/project-uos/...` — Pages 소스가 `/docs`인지 확인)에서 실기기/브라우저 위치 허용 → "안전한 길 찾기" → 실 경로 렌더 확인. mixed-content 없음(둘 다 HTTPS). 콘솔 에러 없음.
Expected: 실사용자 GPS로 서울 어디서든 경로 생성.

---

## Self-Review

- **Spec 커버리지:** Phase 2 `server/app.py`(T3)·`Dockerfile`+`requirements-server`(T3/T4)·프론트 Geolocation/API_BASE/로딩/폴백(T5)·로컬 E2E 먼저 후 Azure(T6→T7)·배포 az 단계(T7)·테스트(pytest T1~T3, playwright T5~T6) 모두 대응. Phase 1(Leaflet)은 이미 커밋됨.
- **플레이스홀더:** 없음(모든 코드·명령 실체 포함). Dockerfile geos/proj는 wheel 우선 + 명시 폴백.
- **타입 일관성:** `gps_map_payload(lat,lon,dest=...)` 반환 키 집합이 T2 스모크·T3 서버·T5 프론트에서 동일. `route_payload` 필드(`label/shade/distance_m/est_time_min/max_risk/segs/pois`)가 T1 테스트·T3 fake·T5 스텁에서 일치.
- **미해결 확인거리:** GitHub Pages 소스가 `/docs`인지(T7 S7에서 확인) · V-World 도메인 허용(T7 S5 폴백).

---

## 실행 현황 & 이어서 할 일 (2026-07-09, 세션 인계)

**브랜치:** `feat/gps-azure-routing` (아직 main 미머지). 이 브랜치를 origin에 push함.

**완료(T1~T6):**
- T1 payload 직렬화 공용화 + 테스트 / T2 `gps_map_payload` 라이브 검증 + dest 분기 테스트 /
  T3 FastAPI 서버(+502 키유출 방지 수정) / T4 Dockerfile+.dockerignore / T5 프론트 GPS 배선 /
  T6 로컬 E2E **통과**(실 GPS→서버→실경로 렌더).
- **성능 수정(T6서 발견):** weather 15분 캐시+예보 raw 공용화(중복 제거)+`build_env_at` 병렬 /
  서버 GPS 프로파일 1.5km. 콜드 45-63s→16-18s, 웜 ~1s. 전체 테스트 87 passed.
- 프론트 타임아웃 75s·콜드 안내·라우트 수 동적 라벨.

**Azure 리소스(이미 생성됨, 이 머신 az 로그인 유지):**
- 구독 `Azure for Students` / 지역 `koreacentral`
- RG `pawtrail-rg` · ACR `pawtrailacr2026uos` · env `pawtrail-env` · app `pawtrail-api`
- 이미지 `pawtrailacr2026uos.azurecr.io/pawtrail-api:v1` (빌드 성공)
- **FQDN:** `https://pawtrail-api.gentlefield-6f045711.koreacentral.azurecontainerapps.io`
- min-replicas=1, 1cpu/2Gi, 시크릿(.env 키 5개) 주입, ALLOW_ORIGINS=*

**⚠️ 현재 상태: 컨테이너 v1 크래시 중** — `engine/routing/graph_build.py:37`이 `scripts.fetch_songpa_graph`를
모듈 레벨 import 하는데 Dockerfile v1이 `scripts/`를 COPY 안 함 → `ModuleNotFoundError: No module named 'scripts'`.
**수정 반영됨:** Dockerfile에 `COPY scripts ./scripts` 추가(이 커밋). **이미지 재빌드는 아직 안 함.**

**이어서 할 일(정확한 명령):**
1. 이미지 재빌드(v2): `az acr build --registry pawtrailacr2026uos --image pawtrail-api:v2 --file server/Dockerfile .`
2. 앱 갱신: `az containerapp update -n pawtrail-api -g pawtrail-rg --image pawtrailacr2026uos.azurecr.io/pawtrail-api:v2`
3. 스모크: `curl https://<FQDN>/api/health` → ok / `curl "https://<FQDN>/api/route?lat=37.5663&lon=126.9779"` (콜드 ~30-45s).
   실패 시 `az containerapp logs show -n pawtrail-api -g pawtrail-rg --tail 100 --type console`.
4. 프론트 FQDN 빌드+배포: `API_BASE="https://<FQDN>" .venv/bin/python scripts/make_app.py` → docs/app 커밋.
5. 최종 whole-branch 리뷰(superpowers:requesting-code-review) — weather.py 캐시/병렬 동시성·make_app.py diff 중점.
6. **main 머지 + push**(GitHub Pages가 서빙하는 브랜치라야 라이브 갱신). Pages 소스가 `/docs`인지 확인.
7. V-World: 그늘 저하 시 콘솔에 `*.azurecontainerapps.io` 도메인 추가.
8. **발표 후 크레딧 절약:** `az containerapp update -n pawtrail-api -g pawtrail-rg --min-replicas 0` 또는 `az group delete -n pawtrail-rg`.

**후속(범위 밖, task chip):** vworld.py 예외 시 키 URL 유출 방지(심층방어) · engine→scripts 결합 정리 · no-dest GPS 멀티 루트 변형.

**SDD 원장(머신 로컬):** `.superpowers/sdd/progress.md` — 태스크별 커밋 SHA·리뷰 결과 기록.
