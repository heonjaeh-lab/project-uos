---
name: routing-engine
description: 조심해야댕 라우팅 엔진(M3)과 동적 리라우팅(M4)을 구현할 때 사용. 송파구 OSM 보행망을 osmnx로 그래프화, 그늘/위험/공사/집회를 반영한 비용함수, A*/Dijkstra 최적 경로, 동네 순환 루프 생성, 공사·집회 폴리곤 교차 시 자동 재계산을 담는다. geo-routing-engineer 에이전트가 사용.
---

# routing-engine — 안전 경로 추천 (M3) + 동적 리라우팅 (M4)

지도 위 보행 그래프에서 **최단이 아니라 가장 안전한** 경로를 찾는다. 결정론적·재현 가능해야 한다(난수 금지, 필요 시 시드 고정).

## 1. 송파구 그래프 구축 (osmnx 2.x)

**1회만 다운로드**해 캐시에 저장하고 재사용한다. 매 실행 다운로드 금지.

```python
import osmnx as ox
ox.settings.use_cache = True
ox.settings.cache_folder = "data/cache"

def build_songpa_graph(path="data/cache/songpa_walk.graphml"):
    import os
    if os.path.exists(path):
        return ox.load_graphml(path)
    G = ox.graph_from_place("Songpa-gu, Seoul, South Korea", network_type="walk")
    ox.save_graphml(G, path)
    return G
```
- 반환은 networkx `MultiDiGraph`. 노드 속성 `x`(경도), `y`(위도). 엣지 속성 `length`(m), `geometry`(선택, shapely LineString).
- 거리·기하 계산은 투영 좌표계에서: `Gp = ox.projection.project_graph(G)` (자동 UTM). 그늘/폴리곤 교차도 투영 CRS에서.
- 최근접 노드: `ox.distance.nearest_nodes(G, X=lon, Y=lat)`.
- `scripts/fetch_songpa_graph.py`로 다운로드를 분리(엔진 import 시 네트워크 타지 않게).

## 2. 엣지 속성 주입
각 엣지에 M1/M2 결과와 위험요소를 얹는다 (스키마 `WalkEdge`와 일치):
- `shade_ratio` (M1 그늘, 0~1)
- `hazards` (list: 예 `["ice","construction"]`) — mock/제보
- `risk_level` (M2 위험지수를 해당 위치 환경으로 평가한 등급)
- `traffic` (낯선 경로 교통량, mock)

## 3. 비용함수 (핵심)
`CostParams`(주입)를 받아 엣지별 비용을 계산한다. 전역 상수 금지.

```
base = length_m / walk_speed_m_per_min      # 예상 시간(분). 속도는 프로필 기본값(M5 대비 인자화)
multiplier = 1
  - cost.shade_bonus * shade_ratio          # 그늘 많을수록 할인 (비용↓)
  + cost.hazard_penalty * (len(hazards)>0)
  + cost.construction_penalty * has_construction
  + cost.assembly_penalty * has_assembly
  + cost.traffic_penalty * traffic_norm
cost = base * max(multiplier, 0.1)          # 음수/0 방지
```
**안전 게이트 (hard-block):** `risk_level == cost.hard_block_level`(기본 `"red"`) 엣지는 비용 가산이 아니라 **탐색에서 제외**한다(비용 `inf` 또는 부분그래프에서 삭제). "위험한 길은 아무리 짧아도 안 감."

계산한 `cost`를 엣지 속성으로 저장: `G[u][v][k]["cost"] = cost`.

## 4. 경로 탐색
```python
import networkx as nx
def find_route(G, orig_node, dest_node, params):
    # red 엣지 제외한 뷰 or 필터
    try:
        path = nx.shortest_path(G, orig_node, dest_node, weight="cost")
    except nx.NetworkXNoPath:
        return RouteResult(node_path=[], reason="안전 경로를 찾지 못했습니다 (위험 구간으로 단절)")
    return assemble_route(G, path)   # 거리·시간·평균그늘·경유 POI·경고 집계
```
- A*가 필요하면 `nx.astar_path(G, o, d, heuristic=haversine_min_time, weight="cost")`. 휴리스틱은 실제 비용을 넘지 않게(admissible): 직선거리/최대보행속도.
- `assemble_route`: 엣지들의 `length_m` 합, `est_time_min`=cost 아닌 실제 시간 합, `avg_shade_ratio`=길이 가중 평균, `max_risk_level`, 반경 내 POI 부착, 경고 문구.

## 5. 동네 순환 루프 생성 (출발=목적)
목표 거리 `target_m`(예: 30분≈2km)를 만족하는 순환 경로:
- 접근: 출발 노드에서 `target_m/2` 반경의 후보 turnaround 노드들을 모아, 각 후보로 **다른 경로로 왕복**(가는 길·오는 길 엣지 겹침 최소화)했을 때 총 길이가 target에 가장 가까운 것을 선택. 후보 정렬은 결정론(노드 id 순).
- 완전 최적화는 불필요. "target±20% 이내, 그늘 비율 높은" 루프면 충분.

## 6. 동적 리라우팅 (M4)
활성 경로 위에 신규 공사/집회 폴리곤이 뜨면 자동 재계산.

```python
from shapely.geometry import shape, LineString
def reroute_if_blocked(G, route, events, params):
    blocked = []
    for e in events:                      # DynamicEvent
        poly = shape(e.polygon)           # GeoJSON → shapely (투영 CRS로 맞출 것)
        for (u, v, k) in route_edges(route):
            line = edge_line(G, u, v, k)  # geometry 없으면 노드 좌표로 LineString 생성
            if line.intersects(poly):
                blocked.append((u, v, k, e.event_type))
    if not blocked:
        return route, None
    # 막힌 엣지 고가중/제외 후 재탐색
    G2 = penalize_edges(G, blocked, params)   # construction/assembly penalty or inf
    new_route = find_route(G2, route.node_path[0], route.node_path[-1], params)
    msg = f"앞쪽 {kor(blocked[0][3])}로 경로를 변경했어요"
    return new_route, msg
```
- 좌표계 주의: 폴리곤과 엣지 라인은 **같은 CRS**에서 교차 판정. 투영 CRS(m) 권장.
- 변경 diff(추가/삭제된 구간)를 `RouteResult.warnings`에 담아 설명 가능하게.

## 검증 관점 (QA와 공유)
- 그래프 로드: 송파구 노드/엣지 수가 0이 아니고, 캐시 재사용 시 재다운로드 안 함.
- 그늘 많은 우회로 vs 짧은 뙤약볕 직선 → 그늘 경로 선택되는지(비용함수 방향).
- red 엣지가 경로에 포함되지 않는지(hard-block).
- 경로 위 공사 폴리곤 → 재계산되고, 새 경로는 폴리곤과 교차하지 않는지.
- 같은 입력 2회 → 동일 경로(결정론).
