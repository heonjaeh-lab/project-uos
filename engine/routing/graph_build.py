"""M3 그래프 구축 — 송파구 캐시 로드 + 엣지 속성 주입.

책임:
1. `data/cache/songpa_walk.graphml`(송파구 실 OSM 보행망, 노드 9967·엣지 28588)을
   `scripts/fetch_songpa_graph.build_songpa_graph`로 **로드만** 한다(재다운로드 금지).
2. 각 엣지에 라우팅에 필요한 속성을 주입한다:
   - `shade_ratio` : **M1(engine.shade)을 실제로 호출**해 계산(재구현 금지).
   - `risk_level`  : **M2(engine.risk)를 실제로 호출**해 등급 산출(재구현 금지).
   - `hazards`     : 위험 태그(mock, 일부 엣지에 결정론적 부여).
   - `traffic`     : 교통량 정규화값(mock).

제약 준수:
- 데이터 mock(그래프만 실 OSM). 그늘용 건물·가로수는 `data/mock/`의 합성 fixture.
- 결정론: 난수 금지. mock 부여는 **노드 id 산술**로만 결정한다(파이썬 `hash()`는
  프로세스마다 salt가 달라 금지).
- 노면온도는 **입력 필드**다. 여기서 mock으로 넣는 값은 관측/합성 "입력"이지
  다른 값에서 "추정"한 것이 아니다(ML 추정 아님).
- 런타임 LLM 호출 없음.
- M5(개인화)/M6(게임화) 로직은 만들지 않는다. `CostParams`/`RiskParams`/`ShadeParams`
  주입구만 열어 둔다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from engine.risk import compute_risk
from engine.schemas import EnvObservation, RiskLevel, RiskParams, Season
from engine.shade import (
    ShadeParams,
    compute_shade_ratios,
    load_buildings,
    load_trees,
)
from scripts.fetch_songpa_graph import build_songpa_graph

SEOUL = ZoneInfo("Asia/Seoul")

DEFAULT_GRAPH_PATH = "data/cache/songpa_walk.graphml"
BUILDINGS_PATH = "data/mock/buildings.json"
TREES_PATH = "data/mock/street_trees.json"

# M1 건물·가로수 mock 클러스터 중심(송파구). 태양 위치 기준점.
SHADE_REF_LAT = 37.483
SHADE_REF_LON = 127.114

# mock 부여 주기(결정론). 노드 id 산술로만 결정 → 재현 가능.
_HAZARD_STAIRS_MOD = 47      # 이 주기 엣지에 일반 위험 태그
_HAZARD_CONSTRUCTION_MOD = 53
_HAZARD_ASSEMBLY_MOD = 59
_RED_HOTSPOT_MOD = 41        # 이 주기 엣지는 노면 과열 hotspot → M2가 red 판정
_TRAFFIC_MOD = 11

# red hotspot 엣지에 주입할 노면온도(입력 mock). M2 하드규칙(>=60℃) 발동값.
_HOTSPOT_SURFACE_C = 62.0


def default_when() -> datetime:
    """기본 태양 시각(여름 아침 08시, tz-aware). 그림자가 길어 그늘 효과가 보임."""
    return datetime(2026, 7, 8, 8, 0, tzinfo=SEOUL)


def default_summer_env() -> EnvObservation:
    """기본(쾌적) 환경 관측. 대부분 엣지가 green이 되도록 온화하게 설정.

    노면온도는 **입력값**이며, 개별 엣지의 red hotspot은 이 값을 덮어써 넣는다
    (추정이 아니라 mock 입력 교체).
    """
    return EnvObservation(
        timestamp=default_when(),
        lat=SHADE_REF_LAT,
        lon=SHADE_REF_LON,
        air_temp_c=24.0,
        humidity_pct=45.0,
        wind_ms=1.5,
        uv_index=3.0,
        pm10=30.0,
        pm25=15.0,
        road_surface_temp_c=40.0,
        season=Season.summer,
    )


def load_songpa_graph(path: str = DEFAULT_GRAPH_PATH):
    """캐시된 송파구 보행 그래프를 로드한다(재다운로드 금지).

    `build_songpa_graph`는 캐시 파일이 있으면 그대로 로드한다. 파일이 없을 때만
    OSM을 받는데, 이 엔진 경로에서는 캐시가 이미 존재해야 한다.
    """
    return build_songpa_graph(path)


def _code(u: Any, v: Any, k: Any, mod: int) -> int:
    """(u, v, k) → [0, mod) 결정론 코드. 파이썬 hash() 금지(salt 비결정)."""
    return (int(u) * 1000003 + int(v) * 97 + int(k)) % mod


def _mock_hazards(u: Any, v: Any, k: Any) -> list[str]:
    """엣지에 부여할 mock 위험 태그(결정론, 일부 엣지에만)."""
    tags: list[str] = []
    if _code(u, v, k, _HAZARD_CONSTRUCTION_MOD) == 0:
        tags.append("construction")
    if _code(u, v, k, _HAZARD_ASSEMBLY_MOD) == 0:
        tags.append("assembly")
    if _code(u, v, k, _HAZARD_STAIRS_MOD) == 0:
        tags.append("stairs")
    return tags


def _mock_traffic(u: Any, v: Any, k: Any) -> float:
    """엣지 교통량 정규화값(mock, 0~1, 결정론)."""
    return _code(u, v, k, _TRAFFIC_MOD) / float(_TRAFFIC_MOD - 1)


def _mock_surface_temp_c(u: Any, v: Any, k: Any, base_surface_c: float) -> float:
    """엣지 노면온도(**입력 mock**). red hotspot 주기 엣지만 과열값으로 교체."""
    if _code(u, v, k, _RED_HOTSPOT_MOD) == 0:
        return _HOTSPOT_SURFACE_C
    return base_surface_c


def _graph_nodes_edges_for_shade(G):
    """M1 `compute_shade_ratios`가 받는 (nodes, edges) dict 목록으로 변환."""
    nodes = [
        {"id": n, "lat": float(d["y"]), "lon": float(d["x"])}
        for n, d in G.nodes(data=True)
    ]
    edges = []
    for u, v, k, d in G.edges(keys=True, data=True):
        geom = d.get("geometry")
        if geom is not None and hasattr(geom, "coords"):
            coords = [[float(x), float(y)] for x, y in geom.coords]
            edges.append(
                {"u": u, "v": v, "geometry": {"type": "LineString", "coordinates": coords}}
            )
        else:
            edges.append({"u": u, "v": v})
    return nodes, edges


def inject_edge_attributes(
    G,
    *,
    env: EnvObservation | None = None,
    when: datetime | None = None,
    risk_params: RiskParams | None = None,
    shade_params: ShadeParams | None = None,
    buildings=None,
    trees=None,
    buildings_path: str = BUILDINGS_PATH,
    trees_path: str = TREES_PATH,
    shade_ref: tuple[float, float] = (SHADE_REF_LAT, SHADE_REF_LON),
):
    """엣지에 `shade_ratio`(M1)·`risk_level`(M2)·`hazards`·`traffic`(mock)을 주입.

    - `shade_ratio` : `engine.shade.compute_shade_ratios`를 **실제 호출**(재구현 금지).
      건물·가로수 mock 근처 엣지만 값을 가진다(그 외 0.0) → "일부 엣지에 부여".
    - `risk_level`  : 엣지별 노면온도(입력 mock)를 넣은 `EnvObservation`으로
      `engine.risk.compute_risk`를 **실제 호출**해 등급을 얻는다(재구현 금지).
    - `hazards`/`traffic` : 결정론 mock.

    같은 그래프·인자면 항상 같은 결과(난수 없음).
    """
    env = env or default_summer_env()
    when = when or default_when()
    risk_params = risk_params or RiskParams()
    shade_params = shade_params or ShadeParams()

    # --- M1: 그늘 비율 계산 (실제 호출) ---
    # buildings/trees 객체를 직접 주면 그걸 쓰고(실데이터 OSM), 없으면 mock 경로 로드.
    if buildings is None:
        buildings = load_buildings(buildings_path)
    if trees is None:
        trees = load_trees(trees_path)
    nodes, edges = _graph_nodes_edges_for_shade(G)
    ref_lat, ref_lon = shade_ref
    shade_ratios = compute_shade_ratios(
        nodes,
        edges,
        buildings,
        trees,
        lat=ref_lat,
        lon=ref_lon,
        when=when,
        params=shade_params,
    )

    # --- M2: 노면온도(입력)별 등급 memo (compute_risk 실제 호출) ---
    #   변화하는 입력은 노면온도뿐이라 값별로 1회만 M2를 돌려 캐시한다(결정론·경량).
    level_cache: dict[float, str] = {}

    def _risk_level_for(surface_c: float) -> str:
        key = round(float(surface_c), 1)
        if key not in level_cache:
            edge_env = env.model_copy(update={"road_surface_temp_c": key})
            level_cache[key] = compute_risk(edge_env, risk_params).level.value
        return level_cache[key]

    for u, v, k, d in G.edges(keys=True, data=True):
        d["shade_ratio"] = float(shade_ratios.get((u, v), 0.0))
        d["hazards"] = _mock_hazards(u, v, k)
        d["traffic"] = _mock_traffic(u, v, k)
        surface_c = _mock_surface_temp_c(u, v, k, env.road_surface_temp_c)
        d["risk_level"] = _risk_level_for(surface_c)

    return G


def build_routing_graph(
    *,
    path: str = DEFAULT_GRAPH_PATH,
    env: EnvObservation | None = None,
    when: datetime | None = None,
    risk_params: RiskParams | None = None,
    shade_params: ShadeParams | None = None,
    buildings=None,
    trees=None,
    shade_ref: tuple[float, float] = (SHADE_REF_LAT, SHADE_REF_LON),
    cost_params=None,
    walk_speed_m_per_min: float | None = None,
):
    """로드 + 속성 주입 + 엣지 비용 계산까지 끝낸 라우팅용 그래프를 만든다.

    편의 함수: `load_songpa_graph` → `inject_edge_attributes` → `compute_edge_costs`.
    `buildings`/`trees`를 주면 그 실데이터로 그늘을 계산한다(없으면 mock).
    `cost_params`/`walk_speed_m_per_min`을 주면 비용까지 계산해 둔다(없으면 기본값).
    """
    from engine.routing.cost import DEFAULT_WALK_SPEED_M_PER_MIN, compute_edge_costs
    from engine.schemas import CostParams

    G = load_songpa_graph(path)
    inject_edge_attributes(
        G,
        env=env,
        when=when,
        risk_params=risk_params,
        shade_params=shade_params,
        buildings=buildings,
        trees=trees,
        shade_ref=shade_ref,
    )
    compute_edge_costs(
        G,
        cost_params or CostParams(),
        walk_speed_m_per_min=walk_speed_m_per_min or DEFAULT_WALK_SPEED_M_PER_MIN,
    )
    return G


__all__ = [
    "DEFAULT_GRAPH_PATH",
    "BUILDINGS_PATH",
    "TREES_PATH",
    "SEOUL",
    "default_when",
    "default_summer_env",
    "load_songpa_graph",
    "inject_edge_attributes",
    "build_routing_graph",
]
