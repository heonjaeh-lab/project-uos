# 00 · 아키텍트 데이터 계약 (M0 스키마)

> 이 문서는 `engine/schemas/`의 **필드·타입·의미**를 정리한 계약서다. 다른 에이전트
> (geo-routing / rules / qa)는 이 shape에 맞춰 구현한다. 스키마를 바꾸면 이 문서도 갱신한다.
>
> - 스키마 도구: **pydantic v2** (`BaseModel`). import: `from engine.schemas import *`
> - 좌표계: **WGS84**. 스칼라 좌표는 `lat`/`lon` 필드로 명시, 튜플은 `(lat, lon)`.
> - 단위: 거리 **m**, 시간 **min**, 온도 **℃**, 각도 **degree**. 필드명 접미사(`_m`, `_min`, `_c`).
> - **GeoJSON 주의:** 지오메트리의 `coordinates`는 사양대로 **`[lon, lat]`** 순서(스칼라 lat/lon과 반대).
> - 결정론·런타임 LLM 금지. 확률/추정 필드 없음. **노면온도는 입력 필드**(`road_surface_temp_c`).

---

## 공통 (`common.py`)

### Coord
| 필드 | 타입 | 기본 | 의미 |
|------|------|------|------|
| `lat` | float (−90~90) | 필수 | 위도(°, WGS84) |
| `lon` | float (−180~180) | 필수 | 경도(°, WGS84) |

메서드 `as_tuple() -> (lat, lon)`.

### 열거형
| 이름 | 값 |
|------|-----|
| `RiskLevel` | `green` \| `yellow` \| `red` |
| `Season` | `summer` \| `winter` \| `shoulder` |

### GeoJSON 지오메트리 (coordinates = `[lon, lat]`)
| 모델 | `type` | `coordinates` 타입 |
|------|--------|--------------------|
| `GeoJSONPoint` | `"Point"` | `[lon, lat]` (position, 길이 2~3) |
| `GeoJSONLineString` | `"LineString"` | `list[position]` (정점 ≥2) |
| `GeoJSONPolygon` | `"Polygon"` | `list[list[position]]` (링, 외곽 우선, 첫=끝) |

`GeoJSONGeometry` = 세 모델의 Union. `Position` = `list[float]`(길이 2~3).

---

## DogProfile (`profile.py`) — M5 개인화의 입력(로직 없음)
| 필드 | 타입 | 기본 | 의미 |
|------|------|------|------|
| `breed` | str | 필수 | 견종명 |
| `age_years` | float (≥0) | 필수 | 나이(년) |
| `weight_kg` | float (>0) | 필수 | 체중(kg) |
| `coat_length` | `CoatLength` {short\|medium\|long} | 필수 | 털 길이 |
| `brachycephalic` | bool | 필수 | 단두종 여부(열 취약) |
| `size_class` | `SizeClass` {toy\|small\|medium\|large} | 필수 | 체급 |
| `conditions` | list[str] | `[]` | 지병 태그(`patella`, `heart`, `obesity` …) |

---

## EnvObservation (`environment.py`) — M2 입력
| 필드 | 타입 | 기본 | 의미 |
|------|------|------|------|
| `timestamp` | datetime | 필수 | 관측 시각(ISO 8601, tz 권장) |
| `lat` / `lon` | float | 필수 | 관측 지점(WGS84) |
| `air_temp_c` | float | 필수 | 기온(℃) |
| `humidity_pct` | float (0~100) | 필수 | 상대습도(%) |
| `wind_ms` | float (≥0) | 필수 | 풍속(m/s) |
| `uv_index` | float (≥0) | 필수 | 자외선 지수 |
| `pm10` | float (≥0) | 필수 | 미세먼지 PM10(µg/m³) |
| `pm25` | float (≥0) | 필수 | 초미세먼지 PM2.5(µg/m³) |
| `road_surface_temp_c` | float | 필수 | **노면온도(℃) — 입력값, 추정 금지** |
| `season` | `Season` | 필수 | 계절 모드 |

---

## WalkNode (`graph.py`)
| 필드 | 타입 | 기본 | 의미 |
|------|------|------|------|
| `id` | int | 필수 | 노드 id(**OSM node id**) |
| `lat` / `lon` | float | 필수 | 좌표(WGS84) |
| `has_streetlight` | bool | `False` | 가로등 인접(야간 안전) |

## WalkEdge (`graph.py`) — `u`→`v` 방향
| 필드 | 타입 | 기본 | 의미 |
|------|------|------|------|
| `u` | int | 필수 | 시작 노드 id |
| `v` | int | 필수 | 끝 노드 id |
| `length_m` | float (≥0) | 필수 | 구간 길이(m) |
| `shade_ratio` | float (0~1) | `0.0` | 그늘 비율 — **M1이 채움** |
| `surface_type` | str | `"unknown"` | 노면 종류(`asphalt`, `paved` …) |
| `hazards` | list[str] | `[]` | 위험 태그(`stairs`, `ice`, `chloride` …) |
| `slope_pct` | float | `0.0` | 경사(%) |
| `has_stairs` | bool | `False` | 계단 포함 |
| `geometry` | `GeoJSONLineString \| None` | `None` | 구간 폴리라인. 없으면 직선 근사 |

> 그래프만은 **송파구 실 OSM** 값(id·좌표·length_m)을 사용한다. 나머지 속성은 mock 기본값 → M1/크라우드소싱이 채운다.

---

## POI (`poi.py`)
| 필드 | 타입 | 기본 | 의미 |
|------|------|------|------|
| `poi_type` | `POIType` | 필수 | 종류(아래) |
| `lat` / `lon` | float | 필수 | 좌표(WGS84) |
| `name` | str | 필수 | 명칭 |
| `open_now` | `bool \| None` | `None` | 영업 여부(모르면 None) |

`POIType` = `toilet`(화장실) \| `water_fountain`(음수대) \| `park`(공원) \| `pet_shop`(펫샵) \| `animal_hospital`(동물병원) \| `poop_bag_station`(배변봉투함).

---

## DynamicEvent (`event.py`) — M4 입력
| 필드 | 타입 | 기본 | 의미 |
|------|------|------|------|
| `event_type` | `EventType` {construction\|assembly} | 필수 | 이벤트 종류 |
| `polygon` | `GeoJSONPolygon` | 필수 | 영향 영역 |
| `start` | datetime | 필수 | 시작 시각 |
| `end` | datetime | 필수 | 종료 시각 |
| `source` | str | 필수 | 출처 |

---

## RouteResult (`route.py`) — M3/M4 출력
| 필드 | 타입 | 기본 | 의미 |
|------|------|------|------|
| `node_path` | list[int] | `[]` | 경유 노드 id 순서(OSM) |
| `polyline` | `GeoJSONLineString \| None` | `None` | 경로 폴리라인. 경로 없으면 None |
| `distance_m` | float (≥0) | `0.0` | 총 거리(m) |
| `est_time_min` | float (≥0) | `0.0` | 예상 소요(min) |
| `avg_shade_ratio` | float (0~1) | `0.0` | 길이 가중 평균 그늘 비율 |
| `max_risk_level` | `RiskLevel` | `green` | 경로 내 최대 위험 등급 |
| `pois_on_route` | list[POI] | `[]` | 경유 POI |
| `warnings` | list[`RouteWarning`] | `[]` | 경고·안내 |
| `reason` | `str \| None` | `None` | 경로 실패 사유(성공 시 None) |

### RouteWarning
| 필드 | 타입 | 기본 | 의미 |
|------|------|------|------|
| `level` | `WarningLevel` {info\|warning\|danger} | 필수 | 심각도 |
| `category` | str | 필수 | 분류(`heat`, `surface`, `construction`, `assembly`, `hazard`, `reroute` …) |
| `message` | str | 필수 | 사용자 안내 문구 |
| `location` | `Coord \| None` | `None` | 관련 지점 |

---

## 파라미터 주입 규약 (`params.py`) — M5 대비 핵심
> M2·M3 함수는 **반드시 이 params 객체를 인자로 받는다(전역 상수 금지)**. M5는 나중에
> `DogProfile → RiskParams/CostParams` 변환 함수만 추가한다. **필드 이름·기본값 계약은 고정**(값만 교체).

### RiskParams (위험지수, 0~100 점수 기준)
| 필드 | 기본 | 의미 |
|------|------|------|
| `heat_weight` | 0.35 | 열지수(기온+습도) 가중 |
| `surface_weight` | 0.30 | 노면온도(발바닥 화상) 가중 |
| `uv_weight` | 0.15 | 자외선 가중 |
| `pm_weight` | 0.20 | 미세먼지 가중 |
| `yellow_threshold` | 40.0 | 노랑 경계 점수 |
| `red_threshold` | 70.0 | 빨강 경계 점수 |

### CostParams (라우팅 비용함수·안전 게이트)
| 필드 | 기본 | 의미 |
|------|------|------|
| `shade_bonus` | 0.4 | 그늘 비율만큼 비용 할인 |
| `hazard_penalty` | 1.5 | 위험요소 페널티 |
| `construction_penalty` | 5.0 | 공사 구간 페널티 |
| `assembly_penalty` | 5.0 | 집회 구간 페널티 |
| `traffic_penalty` | 1.2 | 교통 페널티 |
| `hard_block_level` | `"red"` | 이 위험등급 엣지는 그래프에서 제외 |

### DefaultParams (주입 기본값 묶음)
`DefaultParams.risk` → `RiskParams()`, `DefaultParams.cost` → `CostParams()`.
사용 예: `compute_risk(env, params=DefaultParams.risk)`.

---

## mock 샘플 (`data/mock/`)
| 파일 | 스키마 | 비고 |
|------|--------|------|
| `dog_profile.json` | DogProfile | 소형 푸들, 슬개골(patella) |
| `env_observation.json` | EnvObservation | 여름·노면 51.7℃ 시나리오 |
| `walk_graph.json` | `{nodes:[WalkNode], edges:[WalkEdge]}` | **송파구 실 OSM 5노드·4엣지** |
| `poi.json` | list[POI] | 공원·음수대·동물병원 |
| `dynamic_event.json` | DynamicEvent | 도로굴착 공사 폴리곤(경로 인접) |
| `route_result.json` | RouteResult | 실 OSM 경로 + 리라우팅/노면 경고 |

검증: `.venv/bin/python -c "from engine.schemas import *; print('schemas ok')"` 및 `data/mock` 전건 파싱 통과.
