"""건물·가로수 그림자 폴리곤 → 보행 엣지 그늘 비율(shade_ratio 0~1) 계산 (M1).

여름 산책의 핵심은 그늘이다. 태양 위치(`solar.py`)와 건물 높이·가로수 기하로
각 보행 엣지가 얼마나 그늘에 덮이는지를 순수 기하로 계산한다(ML·추정·난수 없음).

좌표계 주의(흔한 버그): 길이·이동·교차는 반드시 **투영 CRS(m)** 에서 한다.
WGS84(도)에서 length 를 재면 값이 무의미하다. 여기선 `pyproj.Transformer` 로
WGS84(EPSG:4326) → UTM 52N(EPSG:32652, 서울권) 변환 후 계산한다.

M5(개인화)/M6(게임화) 로직은 이번 범위에서 만들지 않는다. 다만 `ShadeParams` 에
파라미터 주입구(투영 CRS·나무 높이 배수·야간 그늘값·개인화 슬롯)를 열어 둔다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping

from pyproj import Transformer
from shapely import STRtree
from shapely.affinity import translate
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import transform as shp_transform
from shapely.ops import unary_union

from engine.shade.solar import SunPosition, shadow_vector, sun_position

# ---------------------------------------------------------------------------
# 입력 모델 (M1 전용 — engine/schemas 는 그래프/환경 계약이라 건물·가로수는 여기 정의)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Building:
    """건물. footprint(외곽 링, WGS84 [lon,lat]) + 높이(m)."""

    footprint: tuple[tuple[float, float], ...]  # 외곽 링, (lon, lat)
    height_m: float
    id: str | int | None = None

    @classmethod
    def from_feature(cls, feat: Mapping[str, Any]) -> "Building":
        """mock feature(dict)에서 생성. `footprint` 는 GeoJSON Polygon(첫 링=외곽)."""
        poly = feat["footprint"]
        ring = poly["coordinates"][0]
        return cls(
            footprint=tuple((float(c[0]), float(c[1])) for c in ring),
            height_m=float(feat["height_m"]),
            id=feat.get("id"),
        )


@dataclass(frozen=True)
class Tree:
    """가로수. 위치(WGS84) + 수관 반경(m)."""

    lat: float
    lon: float
    canopy_radius_m: float
    id: str | int | None = None

    @classmethod
    def from_feature(cls, feat: Mapping[str, Any]) -> "Tree":
        """mock feature(dict)에서 생성."""
        return cls(
            lat=float(feat["lat"]),
            lon=float(feat["lon"]),
            canopy_radius_m=float(feat["canopy_radius_m"]),
            id=feat.get("id"),
        )


@dataclass(frozen=True)
class ShadeParams:
    """그늘 계산 파라미터(주입식). 값만 교체하면 되도록 계약을 고정한다.

    `personalization` 은 M5(견종·건강 개인화) 주입구다 — 이번 범위에선 사용하지
    않고 자리만 열어 둔다(전달돼도 M1 기하 결과는 바뀌지 않는다).
    """

    projected_crs: str = "EPSG:32652"  # UTM 52N (서울권). 길이·이동·교차를 여기서 계산
    geographic_crs: str = "EPSG:4326"  # WGS84 (입력 좌표)
    tree_height_factor: float = 2.0  # 유효 나무 높이 = 수관 반경 × 이 값(그림자 이동량)
    night_shade_ratio: float = 1.0  # 해 진 뒤(고도<=0) 전 구간 그늘 처리 값
    personalization: Mapping[str, Any] | None = None  # M5 주입구(미사용)


# ---------------------------------------------------------------------------
# 좌표 변환 헬퍼
# ---------------------------------------------------------------------------


def _transformer(params: ShadeParams) -> Transformer:
    """WGS84 → 투영 CRS 변환기. always_xy=True → 입력 (lon, lat) 순서."""
    return Transformer.from_crs(
        params.geographic_crs, params.projected_crs, always_xy=True
    )


def _project(geom, transformer: Transformer):
    """shapely 지오메트리(경위도)를 투영 CRS(m)로 변환."""
    return shp_transform(transformer.transform, geom)


def _field(obj: Any, name: str) -> Any:
    """dict 이면 key, 아니면 attribute 로 값을 꺼낸다(WalkEdge/GeoJSON 모델 겸용)."""
    if isinstance(obj, Mapping):
        return obj.get(name)
    return getattr(obj, name, None)


# ---------------------------------------------------------------------------
# 그림자 폴리곤 (투영 CRS)
# ---------------------------------------------------------------------------


def _building_shadow(building: Building, sun: SunPosition, transformer: Transformer):
    """건물 하나의 그림자 폴리곤(투영 CRS). footprint 를 그림자 벡터만큼 쓸어 만든다."""
    vec = shadow_vector(sun.elevation_deg, sun.azimuth_deg, building.height_m)
    poly = _project(Polygon(building.footprint), transformer)
    if vec is None:
        return poly  # 안전상 footprint 자체는 그늘로(사실상 도달 안 함)
    dx, dy = vec
    return unary_union([poly, translate(poly, xoff=dx, yoff=dy)]).convex_hull


def _tree_shadow(tree: Tree, sun: SunPosition, params: ShadeParams, transformer: Transformer):
    """가로수 하나의 그늘 폴리곤(투영 CRS).

    수관을 원으로 보고, 태양 반대편으로 (유효 높이 기준) 이동한 원과의 합집합을
    convex hull 로 감싼다. 태양이 높으면 이동량이 작아 나무 바로 아래 원에 가깝고,
    낮으면 그림자 쪽으로 길게 늘어난다.
    """
    cx, cy = transformer.transform(tree.lon, tree.lat)
    base = Point(cx, cy).buffer(tree.canopy_radius_m)
    height_eff = tree.canopy_radius_m * params.tree_height_factor
    vec = shadow_vector(sun.elevation_deg, sun.azimuth_deg, height_eff)
    if vec is None:
        return base
    dx, dy = vec
    shifted = Point(cx + dx, cy + dy).buffer(tree.canopy_radius_m)
    return unary_union([base, shifted]).convex_hull


def build_shade_union(
    sun: SunPosition,
    buildings: Iterable[Building],
    trees: Iterable[Tree],
    params: ShadeParams,
    transformer: Transformer,
):
    """모든 건물·가로수 그림자의 합집합(투영 CRS)을 만든다.

    해가 졌으면(`sun.elevation_deg <= 0`) 방향 있는 그림자가 없으므로 `None` 을
    돌려주고, 야간 처리는 상위(`compute_shade_ratios`)에서 한다.

    Returns:
        shapely 지오메트리(합집합) 또는 그림자가 없으면 `None`.
    """
    if not sun.is_daylight:
        return None
    parts = []
    for b in buildings:
        parts.append(_building_shadow(b, sun, transformer))
    for t in trees:
        parts.append(_tree_shadow(t, sun, params, transformer))
    if not parts:
        return None
    return unary_union(parts)


# ---------------------------------------------------------------------------
# 엣지 그늘 비율
# ---------------------------------------------------------------------------


def edge_shade_ratio(
    line_lonlat: list[tuple[float, float]],
    shade_union_proj,
    transformer: Transformer,
) -> float:
    """엣지(경위도 폴리라인)가 그늘 합집합에 덮인 길이 비율(0~1)을 구한다.

    Args:
        line_lonlat: 엣지 폴리라인 정점 목록 `[(lon, lat), ...]`.
        shade_union_proj: `build_shade_union` 결과(투영 CRS). `None` 이면 그늘 0.
        transformer: WGS84 → 투영 CRS 변환기.

    Returns:
        `covered_length / edge_length` 를 [0, 1] 로 자른 값.
    """
    line = _project(LineString(line_lonlat), transformer)
    if line.length == 0.0:
        return 0.0
    if shade_union_proj is None:
        return 0.0
    covered = line.intersection(shade_union_proj).length
    return min(covered / line.length, 1.0)


def _edge_line_lonlat(
    edge: Any, node_coord: Mapping[int, tuple[float, float]]
) -> list[tuple[float, float]]:
    """엣지의 폴리라인(경위도)을 얻는다. geometry 없으면 노드 좌표로 직선 근사."""
    geom = _field(edge, "geometry")
    if geom is not None:
        coords = _field(geom, "coordinates")
        if coords:
            return [(float(c[0]), float(c[1])) for c in coords]
    u = _field(edge, "u")
    v = _field(edge, "v")
    return [node_coord[u], node_coord[v]]


def compute_shade_ratios(
    nodes: Iterable[Any],
    edges: Iterable[Any],
    buildings: Iterable[Building],
    trees: Iterable[Tree],
    *,
    lat: float,
    lon: float,
    when: datetime,
    params: ShadeParams | None = None,
) -> dict[tuple[int, int], float]:
    """보행 그래프 각 엣지의 `shade_ratio`(0~1)를 계산한다(결정론).

    같은 입력(노드·엣지·건물·가로수·`when`)이면 항상 같은 결과를 낸다.

    Args:
        nodes: `WalkNode` 또는 `{id, lat, lon}` dict 들.
        edges: `WalkEdge` 또는 `{u, v, geometry?}` dict 들.
        buildings: `Building` 목록.
        trees: `Tree` 목록.
        lat, lon: 태양 위치 계산 기준점(관측 지점, WGS84).
        when: 관측 시각(timezone-aware).
        params: 주입 파라미터(없으면 기본값).

    Returns:
        `{(u, v): shade_ratio}`. 해가 졌으면 전 엣지 `params.night_shade_ratio`.
    """
    params = params or ShadeParams()
    edges = list(edges)
    node_coord = {
        _field(n, "id"): (float(_field(n, "lon")), float(_field(n, "lat")))
        for n in nodes
    }
    sun = sun_position(lat, lon, when)

    result: dict[tuple[int, int], float] = {}
    if not sun.is_daylight:
        for e in edges:
            result[(_field(e, "u"), _field(e, "v"))] = params.night_shade_ratio
        return result

    transformer = _transformer(params)
    # 그림자 파트를 개별 폴리곤으로 만들고 STRtree 로 공간 인덱싱한다.
    # 전체 합집합 1개와 매 엣지를 교차하면 O(엣지 × 전체파트)라 실데이터
    # (건물 ~8천, 엣지 ~2.8만) 규모에서 비현실적으로 느리다. 엣지와 실제로
    # 교차하는 파트만 골라 union 하므로 결과 길이는 전체 union 방식과 동일하다
    # (교차하지 않는 파트는 교차 길이에 0 기여).
    parts = [_building_shadow(b, sun, transformer) for b in buildings]
    parts += [_tree_shadow(t, sun, params, transformer) for t in trees]
    if not parts:
        for e in edges:
            result[(_field(e, "u"), _field(e, "v"))] = 0.0
        return result
    index = STRtree(parts)
    for e in edges:
        key = (_field(e, "u"), _field(e, "v"))
        line = _project(LineString(_edge_line_lonlat(e, node_coord)), transformer)
        if line.length == 0.0:
            result[key] = 0.0
            continue
        hit = index.query(line, predicate="intersects")
        if len(hit) == 0:
            result[key] = 0.0
            continue
        covered = unary_union([parts[i] for i in hit]).intersection(line).length
        result[key] = min(covered / line.length, 1.0)
    return result


# ---------------------------------------------------------------------------
# mock 로더 (data/mock fixtures)
# ---------------------------------------------------------------------------


def load_buildings(path: str) -> list[Building]:
    """`data/mock/buildings.json` → `Building` 목록."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return [Building.from_feature(feat) for feat in data["buildings"]]


def load_trees(path: str) -> list[Tree]:
    """`data/mock/street_trees.json` → `Tree` 목록."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return [Tree.from_feature(feat) for feat in data["trees"]]


def load_graph(path: str) -> tuple[list[dict], list[dict]]:
    """`data/mock/walk_graph.json` → (nodes, edges) dict 목록."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data["nodes"], data["edges"]


__all__ = [
    "Building",
    "Tree",
    "ShadeParams",
    "build_shade_union",
    "edge_shade_ratio",
    "compute_shade_ratios",
    "load_buildings",
    "load_trees",
    "load_graph",
]
