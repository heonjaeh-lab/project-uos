"""M1 그늘/그림자 계산 테스트.

검증 관점(shade-calculation SKILL 및 QA 공유):
- `shade_ratio` 는 항상 0~1.
- 낮은 태양(고도 작음) → 긴 그림자 → 그늘 비율 증가.
- 같은 입력 2회 → 동일 결과(결정론, 난수 없음).

fixtures 는 저장소 루트 기준 상대경로(`data/mock/`)로 로드한다.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from pyproj import Transformer

from engine.shade import (
    ShadeParams,
    SunPosition,
    build_shade_union,
    compute_shade_ratios,
    edge_shade_ratio,
    load_buildings,
    load_graph,
    load_trees,
    shadow_vector,
    sun_position,
)

# 저장소 루트(= tests/ 의 부모)를 기준으로 mock 경로를 만든다.
ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / "data" / "mock" / "walk_graph.json"
BUILDINGS = ROOT / "data" / "mock" / "buildings.json"
TREES = ROOT / "data" / "mock" / "street_trees.json"

SEOUL = ZoneInfo("Asia/Seoul")
# 태양 위치 계산 기준점(송파구 walk_graph 클러스터 중심 부근).
REF_LAT, REF_LON = 37.483, 127.114
# 여름 낮(그림자 짧음) — 정오 지난 14시.
NOON = datetime(2026, 7, 8, 14, 0, tzinfo=SEOUL)


def _load():
    nodes, edges = load_graph(str(GRAPH))
    buildings = load_buildings(str(BUILDINGS))
    trees = load_trees(str(TREES))
    return nodes, edges, buildings, trees


def _ratios(when):
    nodes, edges, buildings, trees = _load()
    return compute_shade_ratios(
        nodes, edges, buildings, trees, lat=REF_LAT, lon=REF_LON, when=when
    )


# ---------------------------------------------------------------------------
# 1. shade_ratio 는 0~1
# ---------------------------------------------------------------------------


def test_shade_ratio_within_unit_interval():
    ratios = _ratios(NOON)
    assert len(ratios) == 4  # walk_graph mock 엣지 수
    for edge, value in ratios.items():
        assert 0.0 <= value <= 1.0, f"{edge} -> {value} 가 [0,1] 범위 밖"


def test_daytime_has_some_shade():
    """엣지 인근에 건물·가로수가 있으므로 낮에는 일부 구간이 그늘에 든다."""
    ratios = _ratios(NOON)
    assert any(v > 0.0 for v in ratios.values())


# ---------------------------------------------------------------------------
# 2. 낮은 태양 → 긴 그림자 → 그늘 증가
# ---------------------------------------------------------------------------


def test_shadow_vector_longer_when_sun_lower():
    """같은 방위·높이에서 태양 고도가 낮을수록 그림자 벡터가 길다."""
    high = shadow_vector(elevation_deg=70.0, azimuth_deg=180.0, height_m=20.0)
    low = shadow_vector(elevation_deg=15.0, azimuth_deg=180.0, height_m=20.0)
    assert high is not None and low is not None
    len_high = (high[0] ** 2 + high[1] ** 2) ** 0.5
    len_low = (low[0] ** 2 + low[1] ** 2) ** 0.5
    assert len_low > len_high


def test_lower_sun_increases_edge_shade():
    """방위 고정(남중, 그림자 정북)일 때 태양이 낮으면 엣지 그늘 비율이 커진다.

    건물 b1 북쪽에 놓인 동서 방향 엣지를 기준으로, 높은 태양(짧은 그림자)은
    엣지에 닿지 못하고 낮은 태양(긴 그림자)은 엣지를 덮는다.
    """
    params = ShadeParams()
    transformer = Transformer.from_crs(
        params.geographic_crs, params.projected_crs, always_xy=True
    )
    buildings = load_buildings(str(BUILDINGS))[:1]  # b1 만 사용
    # b1 footprint 위도 37.48285~37.48300 → 그 북쪽(~37.48327)에 동서 엣지 배치.
    edge_line = [(127.11424, 37.483270), (127.11448, 37.483270)]

    sun_high = SunPosition(elevation_deg=70.0, azimuth_deg=180.0)
    sun_low = SunPosition(elevation_deg=15.0, azimuth_deg=180.0)

    union_high = build_shade_union(sun_high, buildings, [], params, transformer)
    union_low = build_shade_union(sun_low, buildings, [], params, transformer)

    ratio_high = edge_shade_ratio(edge_line, union_high, transformer)
    ratio_low = edge_shade_ratio(edge_line, union_low, transformer)

    assert 0.0 <= ratio_high <= 1.0
    assert 0.0 <= ratio_low <= 1.0
    assert ratio_low > ratio_high


# ---------------------------------------------------------------------------
# 3. 결정론 — 같은 입력 2회 동일
# ---------------------------------------------------------------------------


def test_deterministic_same_input_same_output():
    first = _ratios(NOON)
    second = _ratios(NOON)
    assert first == second


# ---------------------------------------------------------------------------
# 부가: 야간 처리 · tz 요구 · 태양 위치 결정론
# ---------------------------------------------------------------------------


def test_night_all_shaded():
    """해가 진 뒤(고도<=0)에는 전 엣지를 그늘 처리(기본 1.0)."""
    night = datetime(2026, 7, 8, 22, 0, tzinfo=SEOUL)
    ratios = _ratios(night)
    assert ratios  # 비어 있지 않음
    assert all(v == 1.0 for v in ratios.values())


def test_naive_datetime_rejected():
    """tz-naive 시각은 재현성을 해치므로 거부한다."""
    naive = datetime(2026, 7, 8, 14, 0)  # tzinfo 없음
    with pytest.raises(ValueError):
        sun_position(REF_LAT, REF_LON, naive)


def test_sun_position_deterministic():
    a = sun_position(REF_LAT, REF_LON, NOON)
    b = sun_position(REF_LAT, REF_LON, NOON)
    assert a == b
    assert a.is_daylight  # 14시는 낮
