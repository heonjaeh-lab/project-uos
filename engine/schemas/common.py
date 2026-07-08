"""공통 타입·열거형·GeoJSON 지오메트리 모델.

표준(engine-architecture SKILL):
- 좌표계: WGS84. 스칼라 좌표는 `lat`(위도)/`lon`(경도)로 필드명을 명시한다.
- **주의(GeoJSON 순서):** GeoJSON 지오메트리의 `coordinates`는 사양대로 **[lon, lat]**
  순서다(스칼라 lat/lon 필드와 순서가 반대). 저장/전송은 GeoJSON을 사용한다.
- 단위: 거리 m, 시간 min, 온도 ℃, 각도 degree.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# 좌표
# ---------------------------------------------------------------------------


class Coord(BaseModel):
    """WGS84 스칼라 좌표. 튜플 변환은 `(lat, lon)` 순서."""

    lat: float = Field(..., ge=-90.0, le=90.0, description="위도(°, WGS84)")
    lon: float = Field(..., ge=-180.0, le=180.0, description="경도(°, WGS84)")

    def as_tuple(self) -> tuple[float, float]:
        """`(lat, lon)` 튜플로 반환(표준 순서)."""
        return (self.lat, self.lon)


# ---------------------------------------------------------------------------
# 공유 열거형 (여러 모듈에서 참조)
# ---------------------------------------------------------------------------


class RiskLevel(str, Enum):
    """위험 신호등 등급."""

    green = "green"
    yellow = "yellow"
    red = "red"


class Season(str, Enum):
    """계절 모드. 여름=그늘·노면 중심, 겨울=염화칼슘·빙판 중심."""

    summer = "summer"
    winter = "winter"
    shoulder = "shoulder"  # 봄·가을 등 완충기


# ---------------------------------------------------------------------------
# GeoJSON 지오메트리 (coordinates 는 [lon, lat] 순서)
# ---------------------------------------------------------------------------

# GeoJSON position: [lon, lat] 또는 [lon, lat, elevation]
Position = Annotated[
    list[float],
    Field(min_length=2, max_length=3, description="[lon, lat(, elev)] (GeoJSON 순서)"),
]


class GeoJSONPoint(BaseModel):
    """GeoJSON Point."""

    type: str = Field("Point", pattern="^Point$", description="GeoJSON 타입 태그")
    coordinates: Position = Field(..., description="[lon, lat] (WGS84)")


class GeoJSONLineString(BaseModel):
    """GeoJSON LineString(경로 폴리라인 등)."""

    type: str = Field("LineString", pattern="^LineString$", description="GeoJSON 타입 태그")
    coordinates: list[Position] = Field(
        ..., min_length=2, description="정점 목록. 각 정점 [lon, lat]"
    )


class GeoJSONPolygon(BaseModel):
    """GeoJSON Polygon(공사·집회 영역 등). 외곽 링이 첫 번째."""

    type: str = Field("Polygon", pattern="^Polygon$", description="GeoJSON 타입 태그")
    coordinates: list[list[Position]] = Field(
        ...,
        min_length=1,
        description="선형 링 목록(외곽 우선). 각 링은 [lon, lat] 정점, 첫=끝으로 닫힘",
    )


# 지오메트리 유니온 (Field type hint 용)
GeoJSONGeometry = GeoJSONPoint | GeoJSONLineString | GeoJSONPolygon


__all__ = [
    "Coord",
    "RiskLevel",
    "Season",
    "Position",
    "GeoJSONPoint",
    "GeoJSONLineString",
    "GeoJSONPolygon",
    "GeoJSONGeometry",
]
