# Leaflet 지도 가독성 개선 + Azure GPS 라우팅 설계

날짜: 2026-07-08 · 대상: 조심해야댕(PawTrail) 앱 프로토타입

## 문제
1. 앱 지도가 SVG로 그린 가짜 지도라 가독성이 나쁨(길·건물·상호명 없음). 사용자가 실제 지도(네이버 스타일)의 가독성을 원함. 기존 브랜드 느낌은 유지해도 됨.
2. "GPS로 서울 어디든 루트 추천"을 실제로 동작시켜야 함. 엔진(`route_from_gps`)은 서울 전역을 지원하지만 Python이라 정적 배포(GitHub Pages)에서 라이브 계산 불가.

## 결정
- **지도**: Leaflet + OSM 타일 (무료·키 불필요·GitHub Pages 외부 로드 허용).
- **GPS 전달**: Azure(학생 크레딧)에 FastAPI 래퍼를 올려 정적 앱이 HTTPS로 호출. 로컬 API는 https 정적페이지가 http localhost를 막아(mixed-content) 부적합.
- **Azure 타깃**: Container Apps, min replicas=1(캐시 warm 유지, 무료 https). 로컬 Docker 없음 → `az acr build` 클라우드 빌드.

## 아키텍처
```
[GitHub Pages · 정적]                    [Azure · FastAPI(Docker)]
 조심해야댕 앱 (Leaflet)   ──HTTPS──▶  GET /api/route?lat&lon[&dest_lat&dest_lon]
  · 실 OSM 타일 + 경로/마커                 └─ route_from_gps() → 서울 전역
  · "내 위치로 경로" → GPS                  └─ map_data.json 동일 스키마 응답
  · 응답 렌더(실패 시 데모 폴백)            GET /api/health
```
핵심 원칙: 정적 페이지는 항상 데모 경로를 Leaflet로 렌더(오프라인/배포 즉시 동작). GPS 버튼만 Azure 호출. API 장애 시 데모 폴백 → 앱이 안 깨짐.

## Phase 1 — Leaflet 지도 (정적, 먼저 배포 가능)
- `scripts/make_app.py`의 SVG `renderMap`을 Leaflet로 교체. Leaflet JS/CSS는 CDN 로드.
- 경로 `segs`(각 `{line:[[lon,lat]...], shade}`)를 그늘값으로 색칠한 폴리라인: 그늘↑ 청록 / 햇볕↑ 주황. 흰 케이싱 유지.
- 출/착 마커, POI 핀(동물병원·급수대), 산책중 강아지 아바타, 위험구간 하이라이트.
- 브랜드 유지: 주황 #F1592A 액센트, Jua 폰트 UI 크롬 유지 — 지도만 실 타일.

## Phase 2 — Azure GPS 라우팅
- `server/app.py` FastAPI: `GET /api/route` → `route_from_gps` → 기존 export 로직 재사용해 동일 스키마 반환. `GET /api/health`. CORS로 Pages 오리진 허용.
- `server/Dockerfile`: python-slim + geos/proj 시스템 라이브러리, `requirements-server.txt`. 키는 이미지에 굽지 않고 Azure 시크릿(env) 주입. 타일 캐시는 볼륨.
- 프론트: 브라우저 Geolocation → API 호출 → 렌더. 로딩 UI(콜드~30s/캐시~8s), 타임아웃, 실패 폴백. `API_BASE` 상수.

## 배포 (az CLI, 이미 로그인)
1. resource group + ACR 생성 → `az acr build`로 이미지 빌드(로컬 Docker 불필요).
2. Container Apps env + app 생성, min replicas=1, 시크릿으로 키 주입, 8000 포트 ingress(external, https).
3. FQDN 확보 → 프론트 `API_BASE`에 반영 → 재배포.
4. V-World 등록 도메인에 Azure FQDN 추가 필요할 수 있음(서버측 호출).

## 유의점
- 키 로테이션 권장(채팅 노출). git엔 계속 미포함(.env, data/cache, data/demo 제외 유지).
- 런타임 LLM 없음 / 결정론 유지.
- 성능: 콜드 ~30s → 로딩 상태 필수. min replicas=1로 warm 유지.

## 테스트
- 백엔드 pytest: route_from_gps mock 유닛 + env-gated 라이브 스모크.
- 프론트: playwright로 Leaflet 렌더 + geolocation mock→호출→렌더.
- 로컬 E2E 먼저(FastAPI 로컬 → 앱을 localhost로) → 그다음 Azure.
