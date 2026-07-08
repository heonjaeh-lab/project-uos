"""경로 결과 스키마(M3 라우팅·M4 리라우팅 출력)."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from engine.schemas.common import Coord, GeoJSONLineString, RiskLevel
from engine.schemas.poi import POI


class WarningLevel(str, Enum):
    """경고 심각도."""

    info = "info"
    warning = "warning"
    danger = "danger"


class RouteWarning(BaseModel):
    """경로상의 경고·안내 항목(예: '앞쪽 집회로 경로를 변경했어요')."""

    level: WarningLevel = Field(..., description="심각도 {info|warning|danger}")
    category: str = Field(
        ...,
        description="분류(예: 'heat', 'surface', 'construction', 'assembly', 'hazard', 'reroute')",
    )
    message: str = Field(..., description="사용자 안내 문구")
    location: Coord | None = Field(default=None, description="관련 지점(있으면)")


class RouteResult(BaseModel):
    """경로 계산 결과. 경로가 없으면 `node_path`가 비고 `reason`에 사유를 담는다."""

    node_path: list[int] = Field(
        default_factory=list, description="경유 노드 id 순서(OSM node id)"
    )
    polyline: GeoJSONLineString | None = Field(
        default=None, description="경로 폴리라인(GeoJSON LineString). 경로 없으면 None"
    )
    distance_m: float = Field(default=0.0, ge=0.0, description="총 거리(m)")
    est_time_min: float = Field(default=0.0, ge=0.0, description="예상 소요 시간(min)")
    avg_shade_ratio: float = Field(
        default=0.0, ge=0.0, le=1.0, description="구간 길이 가중 평균 그늘 비율(0~1)"
    )
    max_risk_level: RiskLevel = Field(
        default=RiskLevel.green, description="경로 내 최대 위험 등급 {green|yellow|red}"
    )
    pois_on_route: list[POI] = Field(
        default_factory=list, description="경로 주변 경유 POI"
    )
    warnings: list[RouteWarning] = Field(
        default_factory=list, description="경고·안내 목록"
    )
    reason: str | None = Field(
        default=None, description="경로를 못 찾은 사유(성공 시 None)"
    )


__all__ = ["WarningLevel", "RouteWarning", "RouteResult"]
