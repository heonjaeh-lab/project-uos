# 조심해야댕 (PawTrail)

반려견 **안전 산책 & 게임화** 플랫폼. 견종·건강 + 실시간 환경(노면온도·그늘·대기질)을 반영해 가장 안전한 산책 경로를 추천한다. 기준 기획서: `PawTrail_기획서_v3.pdf`, 구현 계획: `docs/구현계획.md`.

## 하네스: 연산 엔진 개발

**목표:** 데이터 수집·디자인 이전에, 결정론 연산 엔진 코어(M0 스키마 · M1 그늘 · M2 위험지수 · M3 라우팅 · M4 동적 리라우팅)를 송파구 대상 + mock 데이터로 구현·검증한다.

**트리거:** 엔진/알고리즘 개발(경로 추천, 위험지수, 그늘 계산, 라우팅, 리라우팅, 스키마) 요청 시 `조심해야댕-orchestrator` 스킬을 사용하라. 단순 질문은 직접 응답 가능.

**핵심 제약:** 언어 Python · 데이터 mock(그래프만 송파구 실 OSM) · 결정론 한정 · 런타임 LLM 금지 · M5(개인화)·M6(게임화)는 별도 기획 중이라 제외(주입구만 열어둠).

**환경:** 개발용 venv는 `.venv/` (osmnx·shapely·pyproj·astral·networkx·pydantic·pytest). 실행: `.venv/bin/python`, `.venv/bin/python -m pytest`.

**변경 이력:**
| 날짜 | 변경 내용 | 대상 | 사유 |
|------|----------|------|------|
| 2026-07-08 | 초기 하네스 구성 (에이전트 4 + 스킬 6) | 전체 | 연산 엔진 코어 개발 착수 |
| 2026-07-08 | 대상 지역 송파구 확정, M5·M6 제외 | orchestrator, 계획서 | 개인화·게임화 별도 기획 중 |
| 2026-07-08 | 엔진 코어 M0~M4 구현 (스키마·그늘·위험지수·라우팅·리라우팅), 테스트 57개 통과 | engine/, tests/ | 워크플로우 에이전트 팀으로 구현 |
| 2026-07-08 | 통합 테스트 직접 보강 (tests/test_integration.py) | tests/ | 워크플로우 최종 QA 에이전트가 no-op(도구호출 0)이라 경계면 검증을 메인이 대체 수행 |
| 2026-07-08 | OSM 실데이터 어댑터 (engine/sources: 건물 7995·POI 300·가로수 83) + STRtree 그늘 최적화 | engine/sources, engine/shade | mock→실 송파구 지형으로 구동 (키 불필요) |
| 2026-07-08 | 라우팅 비용 버그 수정: find_route/neighborhood_loop가 CostParams를 재계산 반영 (recompute_cost) | engine/routing, engine/reroute | find_route가 구운 cost만 써서 넘긴 그늘/위험 가중을 무시하던 함정 — 실데이터 구동 중 발견, 회귀 테스트 추가 |
| 2026-07-08 | 기상·대기질 실데이터 연결 (engine/sources/weather): 단기예보 기온·습도·풍속 + 에어코리아 PM → 위험지수 실측 구동 | engine/sources | API 키는 .env(gitignore). UV·노면온도는 결측 중립처리(자외선 API 미승인, RWIS 없음) |
| 2026-07-08 | 시간별 위험지수(hourly_risk_series) + 다중 경로 추천(recommend_routes 그늘/균형/최단) + 건물높이 면적 휴리스틱(그늘 47→56%) | engine/sources/weather, engine/routing | 위험지수 시간 단위 갱신·경로 다안 선택·그늘 최적화 요구 반영. 회귀 테스트 추가(63개) |
| 2026-07-08 | 대화형 지도 아티팩트(다중경로 클릭선택·GPS 출발·시간별 스트립) + UI 전체 명세(11화면) | docs/오늘의경로_지도.html, docs/UI명세.md | 디자인 착수용 |
| 2026-07-08 | 강수(비) 게이트: EnvObservation 강수필드 + walk_advisory(비/눈→STOP) + 시간별 반영 | engine/schemas, engine/risk/advisory, engine/sources/weather | "비 오면 산책 막기" 요구. 테스트 70개 |
| 2026-07-08 | V-World 실측 건물높이 연동(engine/sources/vworld, 11.7만 동) → 경로 그늘 0.51→0.78 | engine/sources | OSM 휴리스틱 대비 그늘 정확도 대폭↑. 이상치 높이 클램프(≤555m). .env 도메인 필요 |
| 2026-07-08 | GPS 로컬 라우팅 정식 기능(engine/sources/local_routing): 임의 좌표 주변 보행망+건물 온디맨드+타일캐시 → 서울 전역 지원. 기상 격자변환(latlon_to_grid)+build_env_at로 임의좌표 기상 일반화 | engine/sources | "서울 어디서든 GPS 경로" 요구. 콜드~20s/캐시 즉시. 테스트 76개 |
| 2026-07-08 | 작동 앱 프로토타입(docs/app, scripts/make_app.py): '안전한 산책 동반자' 디자인 1:1 재현 + 실데이터 구동(홈/경로/산책중/완료). 시간별 위험지수·다중경로선택·GPS·비게이트·리라우팅 신규 UI | docs/app | 사용자 제작 UI에 엔진 기능 통합. Google폰트+로컬이미지라 파일로 직접 열기(Artifact 아님) |
| 2026-07-09 | 버그 진단(코드 아닌 환경 원인 확정): 라이브 미푸시 구버전 배포 + file:// geolocation 차단 + 네이버키 도메인 미인증. 백엔드·앱코드는 정상 검증(Playwright E2E: 날씨/GPS 경로 Azure 왕복 성공) | (진단) | "날씨 갱신·GPS 경로 안 됨" 원인규명 — Azure는 살아있고 앱은 신버전만 로컬에 있었음 |
| 2026-07-09 | 저장소 리팩토링(T0~T2): 미러 조심해야댕.html·미참조 dog-walk.png·명함 잔재(index.html+assets)·스테일 QA노트 삭제, _workspace→docs/design 이관, make_app TARGETS 정본1개화(부활방지), .gitignore(.superpowers/_workspace) + 로컬 산출물(cache·jpeg·playwright) 청소 | 전체 정리 | "폴더 방대·지저분" 정리, 다음 개선 대비. index.html 정본 md5 불변, pytest 회귀 없음 |
