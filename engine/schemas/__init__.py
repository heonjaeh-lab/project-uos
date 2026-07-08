"""M0 데이터 계약 — 모든 스키마 re-export.

`from engine.schemas import *` 로 모든 모델·열거형·파라미터를 가져온다. 이 계약은
mock 데이터와 실데이터 사이의 교체 가능한 경계이며, 다른 모듈(M1~M4)은 이 shape에
맞춰 구현한다. 스키마를 바꾸면 `_workspace/00_architect_contracts.md`도 갱신한다.
"""

from __future__ import annotations

from engine.schemas.common import (
    Coord,
    GeoJSONGeometry,
    GeoJSONLineString,
    GeoJSONPoint,
    GeoJSONPolygon,
    Position,
    RiskLevel,
    Season,
)
from engine.schemas.environment import EnvObservation
from engine.schemas.event import DynamicEvent, EventType
from engine.schemas.graph import WalkEdge, WalkNode
from engine.schemas.params import CostParams, DefaultParams, RiskParams
from engine.schemas.poi import POI, POIType
from engine.schemas.profile import CoatLength, DogProfile, SizeClass
from engine.schemas.route import RouteResult, RouteWarning, WarningLevel

__all__ = [
    # common
    "Coord",
    "RiskLevel",
    "Season",
    "Position",
    "GeoJSONPoint",
    "GeoJSONLineString",
    "GeoJSONPolygon",
    "GeoJSONGeometry",
    # profile
    "DogProfile",
    "CoatLength",
    "SizeClass",
    # environment
    "EnvObservation",
    # graph
    "WalkNode",
    "WalkEdge",
    # poi
    "POI",
    "POIType",
    # event
    "DynamicEvent",
    "EventType",
    # route
    "RouteResult",
    "RouteWarning",
    "WarningLevel",
    # params
    "RiskParams",
    "CostParams",
    "DefaultParams",
]
