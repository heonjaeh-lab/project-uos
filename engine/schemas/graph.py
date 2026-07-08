"""보행 네트워크 그래프 스키마(노드·엣지).

그래프만은 송파구 실 OSM에서 온 값을 담는다(노드 id·좌표·length_m). 그늘·위험 관련
속성(`shade_ratio`, `hazards`, `slope_pct` 등)은 M1·크라우드소싱이 채우기 전까지
기본값을 가진다. `id`/`u`/`v`는 OSM 노드 id(정수)를 그대로 사용한다.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from engine.schemas.common import GeoJSONLineString


class WalkNode(BaseModel):
    """보행 그래프 노드(교차점·경유점). id 는 OSM node id."""

    id: int = Field(..., description="노드 id(OSM node id)")
    lat: float = Field(..., ge=-90.0, le=90.0, description="위도(°, WGS84)")
    lon: float = Field(..., ge=-180.0, le=180.0, description="경도(°, WGS84)")
    has_streetlight: bool = Field(
        default=False, description="가로등 인접 여부(야간 안전; 미확인 시 False)"
    )


class WalkEdge(BaseModel):
    """보행 그래프 엣지(구간). `u`→`v` 방향(무방향 그래프는 양방향으로 표현)."""

    u: int = Field(..., description="시작 노드 id")
    v: int = Field(..., description="끝 노드 id")
    length_m: float = Field(..., ge=0.0, description="구간 길이(m)")
    shade_ratio: float = Field(
        default=0.0, ge=0.0, le=1.0, description="그늘 비율(0~1) — M1이 채움"
    )
    surface_type: str = Field(
        default="unknown", description="노면 종류(예: 'asphalt', 'paved', 'unknown')"
    )
    hazards: list[str] = Field(
        default_factory=list,
        description="위험 요소 태그(예: 'stairs', 'ice', 'chloride')",
    )
    slope_pct: float = Field(default=0.0, description="경사(%)")
    has_stairs: bool = Field(default=False, description="계단 포함 여부(관절·소형견 회피)")
    geometry: GeoJSONLineString | None = Field(
        default=None, description="구간 폴리라인(GeoJSON LineString). 없으면 직선 근사"
    )


__all__ = ["WalkNode", "WalkEdge"]
