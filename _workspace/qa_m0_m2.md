# QA 리포트 — M0(schemas) · M1(shade) · M2(risk)

> 검증자: qa-verifier / 일자: 2026-07-08
> 실행 파이썬: `.venv/bin/python` (Python 3.13.5, pytest 9.1.1)
> 작업 디렉토리: 프로젝트 루트. "돌아간다"가 아니라 "옳게 돌아간다"를 증거로 확인.

## 1. 전체 테스트 실행 (실제 출력)

```
$ .venv/bin/python -m pytest -q
..........................                                               [100%]
26 passed in 0.24s
```

- **통과 26 / 실패 0.** (test_risk.py 18건, test_shade.py 8건)
- 실패·에러·스킵 없음. 통과 가장 아님 — 아래 경계면·결정론 검증을 별도 스크립트로 직접 재실행해 확인.

## 2. 경계면 교차 비교 (생산자 코드 ↔ 소비자 코드 대조)

### (a) M0 스키마 필드명/단위가 shade·risk에서 실제로 맞게 쓰였는가 — PASS
양쪽 코드를 함께 읽고 대조한 결과 불일치 없음.

- **risk → EnvObservation**: `compute_risk`가 접근하는 필드
  (`air_temp_c`, `humidity_pct`, `road_surface_temp_c`, `uv_index`, `pm25`, `pm10`,
  `season`, `timestamp.hour`)가 모두 `EnvObservation` 스키마 필드명·단위와 일치.
  노면온도는 입력 필드(`road_surface_temp_c`)를 그대로 사용, 추정 없음(제약 준수).
- **shade → WalkNode/WalkEdge**: `_field()`로 `id/lat/lon`(노드), `u/v/geometry`(엣지),
  geometry의 `coordinates`를 접근. 스키마 필드명과 일치.
- **좌표 순서**: shade가 노드/geometry를 `(lon, lat)` 순서로 읽어 `always_xy=True`
  Transformer에 투입 — GeoJSON `[lon,lat]` 계약과 정합. (스칼라 lat/lon과 반대 순서
  주의점을 정확히 지킴.)
- **모델/딕셔너리 겸용 검증**: `_field` 헬퍼가 dict와 pydantic 모델 둘 다 처리.
  실제 `WalkNode/WalkEdge` pydantic 인스턴스로 `compute_shade_ratios`를 돌려도
  dict 입력과 **완전히 동일한 결과**를 냄(다운스트림 라우팅이 모델을 넘겨도 안전).

### (b) risk 결과 level/score shape이 라우팅이 소비 가능한 형태인가 — PASS (주의 1건)
- `RiskResult.score`: `float`, 검증상 항상 `[0,100]`. `RiskResult.level`: `RiskLevel` enum.
- `classify_level(score, params)`가 공개 노출 — 라우팅/게임화 게이트가 공유 가능.
- `RouteResult.max_risk_level: RiskLevel`이 risk 엔진의 `.level`을 그대로 수용함을 확인.
- **주의(설계 노트, 결함 아님)**: 안전 게이트 계약 `CostParams.hard_block_level`은 **`str`
  타입 기본값 `"red"`**인데 생산자 `RiskResult.level`은 **`RiskLevel` enum**이다.
  `RiskLevel`이 `str, Enum` 서브클래스라 `RiskLevel.red == "red"`가 `True`로 평가돼
  **현재는 정상 동작**한다. 다만 M3에서 비교 시 타입 혼용을 인지하고
  `RiskLevel(cost.hard_block_level)`로 정규화해 비교하길 권장(향후 enum 변경 대비).
  → **담당: geo-routing-engineer (M3 안전 게이트 구현 시).**

### (c) shade_ratio가 0~1 범위로 라우팅 비용에 넣기 적합한가 — PASS
- `edge_shade_ratio`가 `min(covered/length, 1.0)`으로 상한 클램프, 길이 0·union None시 0.0.
  야간은 `params.night_shade_ratio`(기본 1.0). 대표 그래프 전 엣지 실측 `[0.139, 0.481]`.
- 값 범위·의미(그늘 비율 0~1)가 `CostParams.shade_bonus`(그늘만큼 비용 할인)의 입력으로 적합.
  방향성(그늘↑→비용↓)은 M3 비용함수가 구현할 몫이며, M1은 올바른 입력값을 생산함을 확인.

## 3. 결정론 (대표 입력 2회 실행 동일)

- **risk**: `env_observation.json`(여름·노면 51.7℃) 2회 → `model_dump()` 완전 동일. (score 68.6 / yellow)
- **shade**: 송파 실 OSM 5노드·4엣지 그래프 + mock 건물·가로수, 14시 2회 → dict 완전 동일.
- pytest 내 `test_deterministic_*`(risk 2건, shade 1건)도 통과. 난수·현재시각 자동조회 없음(제약 준수).

## 4. 발견 이슈

| # | 심각도 | 무엇이 / 어디서 / 어떤 입력 | 담당 |
|---|--------|------------------------------|------|
| 1 | 낮음(설계 노트) | `CostParams.hard_block_level`이 `str`, `RiskResult.level`은 `RiskLevel` enum. str-Enum 서브클래싱 덕에 현재는 `==` 정상. M3 게이트 구현 시 타입 정규화 권장. `engine/schemas/params.py:36` ↔ `engine/risk/risk_index.py:182` | geo-routing-engineer |
| 2 | 정보 | `RiskResult`가 M0 계약 문서(`00_architect_contracts.md`)에 없음. 라우팅과의 교환면은 `RiskLevel`/`score`뿐이라 실무상 문제없으나, M2 출력 계약을 문서에 명시하면 명확. | architect |
| 3 | 정보 | 겨울 모드에서 `dominant="heat"`가 실제로는 저체온(cold) 기여를 의미(코드·필드 설명에 명시됨). 다운스트림 UI 표시 시 계절 분기 필요. `engine/risk/risk_index.py:225` | rules-engineer(참고) |

**큰 설계 이슈 없음.** 위 항목은 모두 후속 모듈(M3) 구현 시 참고할 노트 수준.

## 5. 수정 내역

- **없음.** 오타·필드명 불일치·import 오류 등 명백한 소규모 결함이 발견되지 않아
  직접 수정한 항목 없음. (스키마·shade·risk 전 파일 정독 + import/파싱 실측 확인 완료.)

## 6. 제약 준수 확인

- 언어 Python만 · 데이터 mock(그래프만 송파 실 OSM) · 결정론(난수 없음, tz-aware 강제) ·
  런타임 LLM 호출 없음 · 노면온도는 입력 필드(추정 없음) · M5/M6 로직 미구현(주입구
  `ShadeParams.personalization`, `RiskParams`/`CostParams`만 열려 있음) — 전부 준수.
