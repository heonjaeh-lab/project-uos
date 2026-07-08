"""동적 이벤트 스키마(M4 동적 리라우팅 입력).

공사·집회 등 시간 제약이 있는 영역(폴리곤). 경로 엣지가 이 폴리곤과 교차하면
차단/고가중 처리한다.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from engine.schemas.common import GeoJSONPolygon


class EventType(str, Enum):
    """동적 이벤트 종류."""

    construction = "construction"  # 공사(도로굴착 등)
    assembly = "assembly"  # 집회


class DynamicEvent(BaseModel):
    """활성 기간이 있는 회피 대상 영역."""

    event_type: EventType = Field(..., description="이벤트 종류 {construction|assembly}")
    polygon: GeoJSONPolygon = Field(..., description="영향 영역(GeoJSON Polygon)")
    start: datetime = Field(..., description="시작 시각(ISO 8601)")
    end: datetime = Field(..., description="종료 시각(ISO 8601)")
    source: str = Field(..., description="출처(예: '서울열린데이터광장', '서울경찰청')")


__all__ = ["EventType", "DynamicEvent"]
