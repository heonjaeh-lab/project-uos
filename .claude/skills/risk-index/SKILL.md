---
name: risk-index
description: 조심해야댕 위험지수 엔진(M2)을 구현할 때 사용. 기온·습도·노면온도·자외선·미세먼지를 정규화·가중합해 0~100 위험지수와 신호등(초록/노랑/빨강), 요소별 기여도, 권장 산책 시간대, 계절 모드(여름/겨울)를 산출한다. rules-engineer 에이전트가 사용.
---

# risk-index — 위험지수 엔진 (M2)

반려견 산책 안전을 **설명 가능한 결정론 공식**으로 판단한다. 왜 위험한지(요소별 기여)를 항상 함께 낸다. LLM·확률모델을 쓰지 않는다.

## 입출력
- **입력**: `EnvObservation`(기온·습도·노면온도·자외선·미세먼지·계절) + `RiskParams`(주입) + (선택) `DogProfile`은 이번 범위에선 무시(M5 대비).
- **출력**: `RiskResult { score:0~100, level:{green|yellow|red}, components:{heat,surface,uv,pm}, dominant:str, recommended_windows:list[(start_hour,end_hour)]|None, partial_data:bool }`.

## 4대 요소 → 0~1 정규화 (각 요소의 위험 기여)

각 요소를 "위험 없음 0 ~ 최대 위험 1"로 정규화한 뒤 가중합한다. 상수는 문헌 기반 잠정값 — 반드시 주석에 근거와 `# TODO: 데이터로 보정`.

### 1) 열 스트레스 (heat) — 기온+습도
습도가 높으면 개는 헐떡임으로 체온을 못 내린다. 체감 기반 단순식:
- `apparent = air_temp_c + 0.1 * humidity_pct` (근사 체감; 정식 heat index 대신 경량화)
- 정규화: `heat = clamp((apparent - 24) / (38 - 24), 0, 1)` — 24℃ 이하 0, 38℃(체감) 이상 1.
- (겨울 모드에선 저체온으로 대체 — 아래 계절 모드 참조)

### 2) 노면온도 (surface) — 발바닥 화상
아스팔트 표면온도 기준(자주 인용되는 경험칙): ~43℃부터 불편, ~52℃ 이상 5초 접촉 시 화상 위험, 60℃+ 매우 위험.
- 정규화: `surface = clamp((road_surface_temp_c - 43) / (60 - 43), 0, 1)`.
- 노면온도는 입력값. 결측이면 기온 기반 보수적 추정 금지(ML 영역) → `partial_data=True`, 이 요소는 중립(0).

### 3) 자외선 (uv) — WHO UV Index
0~2 낮음, 3~5 보통, 6~7 높음, 8~10 매우높음, 11+ 위험.
- 정규화: `uv = clamp(uv_index / 11, 0, 1)`.

### 4) 미세먼지 (pm) — 호흡기
PM2.5 등급(㎍/㎥): 0~15 좋음, 16~35 보통, 36~75 나쁨, 76+ 매우나쁨. PM10과 함께 더 나쁜 쪽 채택.
- `pm25_n = clamp(pm25 / 75, 0, 1)`, `pm10_n = clamp(pm10 / 150, 0, 1)`, `pm = max(pm25_n, pm10_n)`.

## 가중합 → 점수 → 신호등
```
score = 100 * (w_heat*heat + w_surface*surface + w_uv*uv + w_pm*pm)   # 가중치 합=1
level = red   if score >= params.red_threshold
        yellow if score >= params.yellow_threshold
        green  otherwise
dominant = 기여도(가중치×정규화값)가 가장 큰 요소
```
**하드 세이프티 규칙(가중합과 별개):** 단일 요소가 극단이면 즉시 red로 승격.
- `road_surface_temp_c >= 60` → red (화상 임박)
- `pm25 >= 76 or pm10 >= 151` → red (매우나쁨)
- `uv_index >= 11` → red
이 규칙은 "평균이 낮아 위험이 희석되는" 문제를 막는다.

## 계절 모드
- **summer**: 위 4요소 그대로. heat·surface·uv 가중 ↑.
- **winter**: heat를 **저체온(cold)**으로 대체 — `cold = clamp((0 - air_temp_c) / (0 - (-15)), 0, 1)` (0℃ 이하부터, -15℃에서 1). 소형·단모종 취약(M5에서 반영). 노면은 빙판/염화칼슘 위험요소로 라우팅(M3)에서 회피 — 위험지수에선 저온만.
- **shoulder(간절기)**: summer 공식, 가중치 중립.

## 권장 산책 시간대
시간대별 예보(`list[EnvObservation]`, 24시간) 입력이 있으면, 각 시각 score를 계산해 `level==green`(없으면 최저 score) 연속 구간을 추천. 없으면 `None`.

## 검증 관점 (QA와 공유)
- 폭염 시나리오(35℃/70%/노면 55℃/UV 9) → red, dominant∈{heat,surface}.
- 쾌적 시나리오(18℃/50%/노면 22℃/UV 2/PM 낮음) → green.
- 노면 60℃ 단일 → 하드 규칙으로 red.
- 미세먼지 결측 → partial_data=True, pm 기여 0.
- 같은 입력 2회 → 동일 결과(결정론).
