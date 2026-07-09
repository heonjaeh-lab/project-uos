# 구름 반영 "실질 그늘"(cloud-aware effective shade) 설계

- 날짜: 2026-07-09
- 상태: 승인됨(사용자) → 구현 진행
- 관련: `engine/shade`, `engine/routing/payload.py`, `engine/sources/local_routing.py`, `engine/sources/weather.py`(sky 이미 수집), `docs/app/index.html`

## 배경 / 문제

현재 그늘 계산(M1, `engine/shade/shade.py`)은 **순수 기하**다 — 태양 위치(astral) + 건물 높이로 그림자 폴리곤을 만들어 엣지별 `shade_ratio`(맑은 하늘 가정)를 낸다. **구름/실제 일조는 전혀 반영하지 않는다.** 그 결과 흐린 날에도 "맑았다면 이만큼 그림자" 값(예: 32%)을 그대로 표시해, 실제로 직사광이 없는데도 그늘이 낮게 보이는 오해를 준다.

기상청 단기예보 하늘상태 SKY는 이미 `engine/sources/weather.py`가 수집해 `EnvObservation.sky_code`(1:맑음 / 3:구름많음 / 4:흐림)로 채우고 있으나, 그늘·표시 로직이 이 값을 사용하지 않는다.

## 목표

"그늘 %"를 **사용자 관점의 실제 햇볕 노출**을 반영하도록 바꾼다: `실질 그늘 = 건물에 안 가려진 정도 × 하늘 맑은 정도`를 뒤집은 값. 흐릴수록 실질 그늘이 100%에 가까워진다(직사광·자외선↓ = 강아지에게 더 안전이라는 신호).

데이터 소스는 **A안(기상청 단기예보 SKY)** — 추가 API 없음, 결정론 유지, 즉시 반영. (실황 운량/위성영상은 후속 과제.)

## 공식 (결정론)

```
sky_clearness(sky_code):
    맑음(1)   -> 1.0
    구름많음(3) -> 0.4
    흐림(4)   -> 0.1
    None/기타  -> 1.0        # 결측 = 맑음 가정(현행 동작 = 회귀 없음)

effective_shade = 1 - (1 - geometric_shade) * clearness
```

예: geo=0.32, 흐림(0.1) → `1 - 0.68*0.1 = 0.932` → 실질 그늘 93%.
성질: clearness=1.0이면 effective == geometric(맑음/결측 시 현행과 동일). geo∈[0,1], clearness∈[0,1] → effective∈[0,1] 보장.

## 계산 위치 — 엔진

프론트에서 JS로 중복 계산하지 않는다. 엔진 payload 조립에서 `env.sky_code`로 clearness를 구해 계산하고, 프론트는 표시만 한다(결정론 엔진 코어 원칙, pytest 검증). payload가 sky를 실어야 하므로 Azure 재배포는 어차피 필요 → 엔진 계산이 정답.

- `engine/shade/`에 순수 함수 추가: `sky_clearness(sky_code) -> float`, `effective_shade(geo, clearness) -> float`.
- `engine/routing/payload.py::route_payload(G, r, label, clearness=1.0)` — 시그니처에 `clearness` 추가(기본 1.0 = 하위호환). route 요약과 각 seg에 `shade_eff` 계산해 부착.
- `engine/sources/local_routing.py::gps_map_payload` — `env.sky_code`로 clearness 산출 → 각 `route_payload(..., clearness=clearness)` 호출. `_weather_meta`에 `sky_code`, `clearness` 추가.
- `scripts/export_map_data.py`(데모 스냅샷 빌더)도 동일하게 clearness 전달(그늘 색칠 일관성). 데모 재베이크 후 `make_app.py`로 `const DATA` 갱신.

## payload 변경 (하위호환)

- 유지(불변): `route.shade`, `seg.shade` = 기하값 그대로. 라우팅 비용/그래프도 불변.
- 추가: `route.shade_eff`, `seg.shade_eff`(실질 그늘), `meta.sky_code`, `meta.clearness`.
- 프론트: `shade_eff`가 있으면 그것으로 표시(없으면 `shade`로 폴백 — 구버전 payload/데모 안전).

## 적용 범위 (YAGNI)

- ✅ 경로 카드 그늘 표시 → 실질 그늘 + 하늘 배지. 맑음 "그늘 32% · ☀️맑음" / 흐림 "실질 그늘 93% · ☁️흐림".
- ✅ 지도 세그먼트 색칠 → `shade_eff` 기준.
- ⛔ **라우팅 경로 선택(비용함수)은 기하 그늘 유지** — 날씨로 추천 경로 자체가 바뀌지 않게(안정성·결정론). 표시 숫자만 정직해짐.
- ⛔ 비(rain) 게이트 우선순위 유지 — 비 오면 STOP·"그늘 —"(cloud 보정은 비가 아닐 때만 의미).
- ⛔ 위험지수(M2)의 UV/열 구름 반영은 이번 범위 밖(후속 과제).

## 실패안전

- `sky_code=None` → clearness=1.0 → effective==geometric → 기존과 완전 동일(회귀 없음).
- 야간: 기하 그늘이 이미 ~전면(shade.py 야간 처리) → 그대로. cloud 보정 얹어도 여전히 높음, 충돌 없음.
- 잘못된 sky_code 값(2 등 미사용/이상치) → 1.0 폴백.

## 테스트

- `sky_clearness`: 1→1.0, 3→0.4, 4→0.1, None→1.0, 이상치→1.0.
- `effective_shade`: 맑음이면 geo와 동일, 흐림이면 상승, 경계값(geo=0,1) [0,1] 유지.
- `route_payload`: `clearness=1.0`이면 `shade_eff==shade`(회귀), `clearness<1`이면 `shade_eff>=shade`, raw `shade`/`seg.shade` 보존, `shade_eff`/`seg.shade_eff` 존재.
- `gps_map_payload`(mock env) / `_weather_meta`: `meta.sky_code`·`meta.clearness` 포함.
- 결정론: 동일 입력 동일 출력.

## 배포

엔진 payload가 바뀌므로 Azure 이미지 재빌드(`az acr build` → `containerapp update`) + 프론트 `docs/app/index.html` push(GitHub Pages). 스모크: `/api/route`가 `shade_eff`/`meta.sky_code` 포함, 흐림 좌표에서 effective > geometric 확인.
