"""환경 관측 스키마(M2 위험지수 엔진 입력).

**노면온도(`road_surface_temp_c`)는 추정하지 않고 입력받는 필드다.** 노면온도
추정 회귀 모델(ASOS→RWIS)은 데이터 확보 후의 ML 과제이며 이번 범위 밖이다.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from engine.schemas.common import Season


class EnvObservation(BaseModel):
    """특정 시각·지점의 환경 관측값. 결정론 계산의 입력."""

    timestamp: datetime = Field(..., description="관측 시각(ISO 8601, tz 권장)")
    lat: float = Field(..., ge=-90.0, le=90.0, description="관측 지점 위도(°, WGS84)")
    lon: float = Field(..., ge=-180.0, le=180.0, description="관측 지점 경도(°, WGS84)")
    air_temp_c: float = Field(..., description="기온(℃)")
    humidity_pct: float = Field(..., ge=0.0, le=100.0, description="상대습도(%)")
    wind_ms: float = Field(..., ge=0.0, description="풍속(m/s)")
    uv_index: float = Field(..., ge=0.0, description="자외선 지수(UV Index)")
    pm10: float = Field(..., ge=0.0, description="미세먼지 PM10(µg/m³)")
    pm25: float = Field(..., ge=0.0, description="초미세먼지 PM2.5(µg/m³)")
    road_surface_temp_c: float = Field(
        ...,
        description="노면온도(℃) — 입력값. 추정 금지, 관측/합성값을 그대로 받는다",
    )
    season: Season = Field(..., description="계절 모드 {summer|winter|shoulder}")


__all__ = ["EnvObservation"]
