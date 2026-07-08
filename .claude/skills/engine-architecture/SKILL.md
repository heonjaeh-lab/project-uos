---
name: engine-architecture
description: 조심해야댕 연산 엔진의 데이터 계약(스키마)·모듈 인터페이스·Python 프로젝트 레이아웃을 설계할 때 사용. pydantic 스키마 표준, 파라미터 주입 규약, 좌표·단위 표준, 패키지 구조를 정의한다. architect 에이전트가 M0를 만들 때 반드시 따른다.
---

# engine-architecture — 엔진 뼈대 설계

조심해야댕 연산 엔진의 데이터 계약과 모듈 경계를 설계한다. 여기서 정한 스키마 위에서 M1~M4가 구현된다.

## 왜 스키마가 먼저인가
데이터 수집이 진행 중이다. 스키마를 먼저 확정하면 (1) 수집팀이 채울 형식이 정해지고, (2) 각 엔진 모듈이 mock 데이터로 즉시 개발을 시작할 수 있다. 스키마는 실데이터와 mock 사이의 **교체 가능한 계약**이다.

## 표준 (반드시 준수)
- **좌표**: WGS84. `lat`(위도), `lon`(경도) 순서로 필드명 명시. 튜플은 `(lat, lon)`.
- **단위**: 거리 m, 시간 min, 온도 ℃, 각도 degree. 필드명에 단위 접미사 권장(`length_m`, `est_time_min`, `temp_c`).
- **지오메트리**: GeoJSON 호환 dict 또는 shapely 객체. 저장/전송은 GeoJSON.
- **스키마 도구**: `pydantic` v2 (`BaseModel`). 필드마다 `Field(..., description=...)`로 의미·출처 명시.
- **결정론·런타임 LLM 금지**: 스키마에 확률/추정 필드를 넣지 않는다. 노면온도는 *입력 필드*(`road_surface_temp_c`)다.

## 프로젝트 레이아웃
```
engine/
  __init__.py
  schemas/
    __init__.py       # 모든 스키마 re-export
    common.py         # Coord, GeoJSONGeometry 등 공통 타입
    profile.py        # DogProfile (M5 대비 필드만, 로직 없음)
    environment.py    # EnvObservation (기온·습도·노면온도·자외선·미세먼지)
    graph.py          # WalkNode, WalkEdge
    poi.py            # POI (화장실·음수대·공원·펫샵·동물병원·배변봉투함)
    event.py          # DynamicEvent (공사·집회 폴리곤)
    route.py          # RouteResult, RouteWarning
    params.py         # RiskParams, CostParams, DefaultParams (주입 규약)
  shade/              # M1 (geo-routing)
  risk/               # M2 (rules)
  routing/            # M3 (geo-routing)
  reroute/            # M4 (geo-routing)
data/
  mock/               # fixtures (JSON/GeoJSON)
  cache/              # OSM 그래프 캐시 (gitignore)
tests/                # pytest
scripts/              # fetch_songpa_graph.py 등
requirements.txt
```

## 핵심 스키마 정의 (M0)

각 모듈이 주고받는 최소 필드. 실데이터 컬럼이 늘면 확장하되 하위 호환 유지.

- **DogProfile**: `breed:str, age_years:float, weight_kg:float, coat_length:{short|medium|long}, brachycephalic:bool, size_class:{toy|small|medium|large}, conditions:list[str]`. (M5 개인화가 이 값을 파라미터로 변환 — 지금은 필드만.)
- **EnvObservation**: `timestamp, lat, lon, air_temp_c, humidity_pct, wind_ms, uv_index, pm10, pm25, road_surface_temp_c, season:{summer|winter|shoulder}`.
- **WalkNode**: `id:int, lat, lon, has_streetlight:bool=False`.
- **WalkEdge**: `u:int, v:int, length_m:float, shade_ratio:float=0.0, surface_type:str="unknown", hazards:list[str]=[], slope_pct:float=0.0, has_stairs:bool=False, geometry:LineString|None`.
- **POI**: `poi_type:enum, lat, lon, name:str, open_now:bool|None`.
- **DynamicEvent**: `event_type:{construction|assembly}, polygon:GeoJSON, start, end, source:str`.
- **RouteResult**: `node_path:list[int], polyline:GeoJSON(LineString), distance_m, est_time_min, avg_shade_ratio, max_risk_level:{green|yellow|red}, pois_on_route:list[POI], warnings:list[RouteWarning], reason:str|None`(경로 없음 사유).

## 파라미터 주입 규약 (M5 대비 — 이번 범위의 핵심 설계)
위험 임계값·비용 가중치를 코드에 하드코딩하지 말고 **주입식**으로 만든다.

```python
# engine/schemas/params.py
class RiskParams(BaseModel):
    heat_weight: float = 0.35
    surface_weight: float = 0.30
    uv_weight: float = 0.15
    pm_weight: float = 0.20
    yellow_threshold: float = 40.0   # 0~100 점수 기준
    red_threshold: float = 70.0
    # TODO: 실측/체감 피드백으로 보정

class CostParams(BaseModel):
    shade_bonus: float = 0.4      # 그늘 비율만큼 비용 할인
    hazard_penalty: float = 1.5
    construction_penalty: float = 5.0
    assembly_penalty: float = 5.0
    traffic_penalty: float = 1.2
    hard_block_level: str = "red"  # 이 위험등급 엣지는 그래프에서 제외

class DefaultParams:
    risk = RiskParams()
    cost = CostParams()
```
나중에 M5(개인화)는 `DogProfile → RiskParams/CostParams`를 만드는 함수만 추가하면 된다. M2·M3 함수는 반드시 이 params를 인자로 받아야 한다(전역 상수 금지).

## 인터페이스 요약 산출
스키마 정의 후 `_workspace/00_architect_contracts.md`에 각 스키마의 필드·타입·의미를 표로 정리한다. 다른 에이전트는 이 파일을 읽고 shape을 맞춘다. 스키마를 바꾸면 이 파일도 갱신한다.

## 검증
- `python -c "from engine.schemas import *"`가 에러 없이 import 되는가.
- 각 스키마에 대응하는 mock 샘플이 `data/mock/`에 1개 이상 있고, 스키마로 파싱되는가.
