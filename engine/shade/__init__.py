"""M1 그늘/그림자 계산 패키지.

태양 위치(`solar`)와 건물·가로수 기하(`shade`)로 보행 엣지별 그늘 비율
(`shade_ratio` 0~1)을 결정론적으로 산출한다. 순수 기하 — ML·추정·난수 없음.

공개 API:
    from engine.shade import (
        SunPosition, sun_position, shadow_vector,   # solar
        Building, Tree, ShadeParams,                # 입력·파라미터
        build_shade_union, edge_shade_ratio, compute_shade_ratios,
        load_buildings, load_trees, load_graph,
    )
"""

from __future__ import annotations

from engine.shade.shade import (
    Building,
    ShadeParams,
    Tree,
    build_shade_union,
    compute_shade_ratios,
    edge_shade_ratio,
    load_buildings,
    load_graph,
    load_trees,
)
from engine.shade.solar import SunPosition, shadow_vector, sun_position

__all__ = [
    # solar
    "SunPosition",
    "sun_position",
    "shadow_vector",
    # inputs / params
    "Building",
    "Tree",
    "ShadeParams",
    # geometry / pipeline
    "build_shade_union",
    "edge_shade_ratio",
    "compute_shade_ratios",
    # mock loaders
    "load_buildings",
    "load_trees",
    "load_graph",
]
