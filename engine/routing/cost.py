"""M3 비용함수 — 엣지별 라우팅 비용과 안전 게이트(hard-block).

`CostParams`(주입)를 받아 각 보행 엣지의 비용을 계산한다. 전역 상수(가중치)를
코드에 박지 않고 파라미터로 주입받는다(계약 `engine/schemas/params.py`).

비용 공식(routing-engine SKILL 3장):
    base       = length_m / walk_speed_m_per_min          # 예상 시간(분)
    multiplier = 1
                 - shade_bonus * shade_ratio              # 그늘 많을수록 할인
                 + hazard_penalty      * (기타 위험태그 존재)
                 + construction_penalty * (공사)
                 + assembly_penalty     * (집회)
                 + traffic_penalty      * traffic_norm
    cost       = base * max(multiplier, 0.1)              # 음수/0 방지

안전 게이트: `risk_level == params.hard_block_level`(기본 "red") 엣지는 가산이
아니라 탐색에서 제외한다 → 비용 `inf`. "위험한 길은 아무리 짧아도 안 감."

`walk_speed_m_per_min`은 프로필 기본값(성인 보행)이며 M5(개인화)에서 견종·체급별
값으로 교체할 수 있게 **인자로 주입**한다(스키마 계약 CostParams는 건드리지 않음).
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping

from engine.schemas import CostParams, RiskLevel

# 성인 보행 기본 속도(약 4.5 km/h). 전역 상수가 아니라 주입 가능한 기본값이다.
# M5에서 DogProfile→속도 변환으로 교체(함수 인자로 넘김).
DEFAULT_WALK_SPEED_M_PER_MIN = 75.0

# 이벤트성 위험은 hazards 태그로 표현(M4 리라우팅과 공유). 나머지 태그는 일반 위험.
CONSTRUCTION_TAG = "construction"
ASSEMBLY_TAG = "assembly"


def _risk_str(risk_level: Any) -> str:
    """RiskLevel enum/str 무엇이 와도 값 문자열로 정규화."""
    if isinstance(risk_level, RiskLevel):
        return risk_level.value
    return str(risk_level)


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def edge_cost(
    *,
    length_m: float,
    shade_ratio: float,
    hazards: Iterable[str] | None,
    risk_level: Any,
    traffic: float,
    params: CostParams,
    walk_speed_m_per_min: float = DEFAULT_WALK_SPEED_M_PER_MIN,
) -> float:
    """엣지 하나의 라우팅 비용(분 단위 스케일). red 등급은 `inf`(탐색 제외).

    Args:
        length_m: 구간 길이(m, 실 OSM).
        shade_ratio: M1 그늘 비율(0~1) — 클수록 비용 할인.
        hazards: 위험 태그 목록(`construction`/`assembly`/`ice`/`stairs` …).
        risk_level: M2 위험 등급(green/yellow/red). `hard_block_level`이면 `inf`.
        traffic: 교통량 정규화값(0~1, mock).
        params: 주입된 `CostParams`(가중치·게이트 등급).
        walk_speed_m_per_min: 보행 속도(주입, M5 대비).

    Returns:
        비용(float). 안전 게이트에 걸리면 `math.inf`.
    """
    if walk_speed_m_per_min <= 0.0:
        raise ValueError("walk_speed_m_per_min 은 0보다 커야 한다")

    # 안전 게이트(hard-block): 가산이 아니라 탐색에서 제외.
    if _risk_str(risk_level) == params.hard_block_level:
        return math.inf

    base = length_m / walk_speed_m_per_min

    tags = list(hazards or [])
    has_construction = CONSTRUCTION_TAG in tags
    has_assembly = ASSEMBLY_TAG in tags
    other_hazards = [t for t in tags if t not in (CONSTRUCTION_TAG, ASSEMBLY_TAG)]
    traffic_norm = _clamp01(float(traffic or 0.0))

    multiplier = 1.0
    multiplier -= params.shade_bonus * _clamp01(float(shade_ratio or 0.0))
    if other_hazards:
        multiplier += params.hazard_penalty
    if has_construction:
        multiplier += params.construction_penalty
    if has_assembly:
        multiplier += params.assembly_penalty
    multiplier += params.traffic_penalty * traffic_norm

    return base * max(multiplier, 0.1)


def _get(d: Mapping[str, Any] | Any, name: str, default: Any = None) -> Any:
    if isinstance(d, Mapping):
        return d.get(name, default)
    return getattr(d, name, default)


def compute_edge_costs(
    G,
    params: CostParams,
    *,
    walk_speed_m_per_min: float = DEFAULT_WALK_SPEED_M_PER_MIN,
) -> Any:
    """그래프의 모든 엣지에 `cost` 속성을 계산해 저장(in place).

    엣지 속성은 `graph_build.inject_edge_attributes`가 미리 주입한
    `shade_ratio`/`hazards`/`risk_level`/`traffic` + 실 OSM `length`를 읽는다.
    """
    for _u, _v, _k, d in G.edges(keys=True, data=True):
        d["cost"] = edge_cost(
            length_m=float(_get(d, "length", 0.0) or 0.0),
            shade_ratio=float(_get(d, "shade_ratio", 0.0) or 0.0),
            hazards=_get(d, "hazards", []),
            risk_level=_get(d, "risk_level", RiskLevel.green.value),
            traffic=float(_get(d, "traffic", 0.0) or 0.0),
            params=params,
            walk_speed_m_per_min=walk_speed_m_per_min,
        )
    return G


__all__ = [
    "DEFAULT_WALK_SPEED_M_PER_MIN",
    "CONSTRUCTION_TAG",
    "ASSEMBLY_TAG",
    "edge_cost",
    "compute_edge_costs",
]
