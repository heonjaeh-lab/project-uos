"""관심지점(POI) 스키마. 경로 경유·편의시설 안내에 사용."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class POIType(str, Enum):
    """POI 종류(기획서 편의시설 집합)."""

    toilet = "toilet"  # 화장실
    water_fountain = "water_fountain"  # 음수대
    park = "park"  # 공원
    pet_shop = "pet_shop"  # 펫샵
    animal_hospital = "animal_hospital"  # 동물병원
    poop_bag_station = "poop_bag_station"  # 배변봉투함


class POI(BaseModel):
    """관심지점. 좌표는 WGS84 스칼라(lat/lon)."""

    poi_type: POIType = Field(..., description="POI 종류")
    lat: float = Field(..., ge=-90.0, le=90.0, description="위도(°, WGS84)")
    lon: float = Field(..., ge=-180.0, le=180.0, description="경도(°, WGS84)")
    name: str = Field(..., description="명칭")
    open_now: bool | None = Field(
        default=None, description="현재 영업 여부(모르면 None)"
    )


__all__ = ["POIType", "POI"]
