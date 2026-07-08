---
name: shade-calculation
description: 조심해야댕 그늘/그림자 계산(M1)을 구현할 때 사용. 태양 위치(고도·방위)를 astral로 구하고, 건물 높이·가로수로 그림자 폴리곤을 만들어 보행 그래프 각 엣지의 그늘 비율(shade_ratio 0~1)을 산출한다. 기하 계산이며 ML이 아니다. geo-routing-engineer 에이전트가 사용.
---

# shade-calculation — 그늘/그림자 계산 (M1)

여름 산책의 핵심은 그늘이다. 태양 위치와 건물·가로수 기하로 각 보행 엣지가 **얼마나 그늘에 덮이는지**를 계산한다. 순수 기하 — ML/추정이 아니다.

## 입출력
- **입력**: 보행 그래프 엣지들, 건물(footprint 폴리곤 + 높이 m), 가로수(위치 + 수관 반경 m), 관측 시각·위치(태양 위치 계산용).
- **출력**: 각 엣지의 `shade_ratio`(0~1) — 엣지 길이 중 그늘에 덮인 비율.

## 1. 태양 위치 (astral)
```python
from astral import Observer
from astral.sun import elevation, azimuth
obs = Observer(latitude=lat, longitude=lon)
sun_elev = elevation(obs, dt)   # 도. 지평선 위 각도
sun_azim = azimuth(obs, dt)     # 도. 북=0, 동=90, 남=180, 서=270 (태양이 있는 방향)
```
- `dt`는 timezone-aware (Asia/Seoul). 시각을 인자로 받아 결정론 유지(현재시각 자동조회 금지 — 재현성).
- `sun_elev <= 0`(해 짐)이면 전 구간 그늘 처리(`shade_ratio=1.0`)하거나 야간 로직 분리.

## 2. 그림자 방향·길이
- **그림자 방향** = 태양 반대편: `shadow_azimuth = (sun_azim + 180) % 360`.
- **그림자 길이**: `L = height_m / tan(radians(sun_elev))` (sun_elev>0). 태양이 낮을수록 그림자 김.
- 방위각을 평면 벡터로: 방위 θ(북기준 시계방향)에서 `dx = L*sin(radians(θ))`, `dy = L*cos(radians(θ))` (동=+x, 북=+y). **투영 CRS(m)에서** 계산.

## 3. 그림자 폴리곤 (건물)
건물 footprint를 그림자 벡터만큼 밀어 "휩쓸린 영역"을 만든다:
```python
from shapely.affinity import translate
from shapely.ops import unary_union
shadow = unary_union([footprint, translate(footprint, xoff=dx, yoff=dy)]).convex_hull
# 여러 건물의 그림자를 합집합
building_shadow = unary_union([shadow_i for each building])
```
- 단순화: footprint와 이동본의 convex hull이면 대부분의 도로 그늘 판정에 충분. 정밀 필요 시 각 변을 쓸어 만든 폴리곤.

## 4. 가로수 그늘
가로수는 점 + 수관 반경. 태양이 높으면 나무 바로 아래, 낮으면 그림자쪽으로 치우침. 실용 근사:
```python
from shapely.geometry import Point
tree_center = Point(tx, ty).buffer(0)  # 투영 좌표
# 수관 그림자: 나무 위치를 그림자 방향으로 (canopy만큼) 이동한 원
shadow_center = translate(Point(tx, ty), xoff=dx_t, yoff=dy_t).buffer(canopy_radius_m)
tree_shadow = unary_union([Point(tx,ty).buffer(canopy_radius_m), shadow_center])
```
- 태양 고도가 높으면(여름 정오) 이동량 작음 → 나무 아래 원에 가깝게.

## 5. 엣지 그늘 비율
```python
shade_union = unary_union([building_shadow, tree_shadow_union])
def edge_shade_ratio(edge_line_projected):
    if edge_line_projected.length == 0: return 0.0
    covered = edge_line_projected.intersection(shade_union).length
    return min(covered / edge_line_projected.length, 1.0)
```
- 엣지 `geometry`가 없으면 노드 좌표로 LineString 생성 후 투영.
- 결과를 엣지 속성 `shade_ratio`로 저장 → M3 비용함수가 사용.

## 좌표계 주의 (흔한 버그)
- 길이·이동·교차는 **투영 CRS(m)**에서. WGS84(도)에서 length를 재면 값이 무의미하다.
- `pyproj.Transformer`로 WGS84 → UTM 52N(EPSG:32652, 서울권) 변환 후 계산, 필요 시 되돌린다. osmnx `project_graph`/`project_gdf`도 활용.

## 검증 관점 (QA와 공유)
- 낮은 태양(아침/저녁, elev 작음) → 그림자 길이 ↑ → 그늘 비율 ↑.
- 정오 고태양 → 그림자 짧음 → 건물 그늘 ↓.
- 큰 건물 북쪽 도로(그림자 방향) 엣지 → 높은 shade_ratio.
- shade_ratio는 항상 0~1.
- 같은 시각·기하 2회 → 동일 결과(결정론).
