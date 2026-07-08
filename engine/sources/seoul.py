"""서울 열린데이터광장 어댑터 (SEOUL_OPEN_DATA_KEY — 키 유효성 확인됨).

키는 정상 작동하나, 각 데이터셋의 **서비스명**이 필요하다(사이트가 JS 렌더라 서비스명
자동 확보 불가). 서비스명(+필드명)을 넘기면 즉시 동작한다:
- 도로굴착 공사 → M4 `DynamicEvent`(construction 폴리곤) — 점 좌표를 소형 폴리곤으로 버퍼
- 아리수 음수대 → `POI`(water_fountain)

서울 API: http://openapi.seoul.go.kr:8088/{키}/json/{서비스명}/{start}/{end}/
응답: {서비스명: {list_total_count, RESULT:{CODE,MESSAGE}, row:[...]}}
"""

from __future__ import annotations

import math
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from engine.schemas import POI, DynamicEvent, EventType, POIType
from engine.sources import config

BASE = "http://openapi.seoul.go.kr:8088"
SEOUL = ZoneInfo("Asia/Seoul")
# 공사 기간이 데이터에 없을 때: "항상 활성"으로 간주(안전하게 회피).
_FAR_PAST = datetime(2000, 1, 1, tzinfo=SEOUL)
_FAR_FUTURE = datetime(2100, 1, 1, tzinfo=SEOUL)


def rows(service: str, start: int = 1, end: int = 1000) -> list[dict]:
    """서울 OpenAPI 서비스에서 row 목록을 받는다. 실패/키없음/에러코드면 []."""
    key = config.get_key("SEOUL_OPEN_DATA_KEY")
    if not key or not service:
        return []
    try:
        j = requests.get(f"{BASE}/{key}/json/{service}/{start}/{end}/", timeout=20).json()
    except Exception:
        return []
    body = j.get(service) or {}
    code = (body.get("RESULT") or {}).get("CODE")
    if code not in (None, "INFO-000"):
        return []
    return body.get("row", []) or []


def _num(row, *keys):
    """행에서 후보 키들 중 첫 숫자값을 반환(대소문자·별칭 대응)."""
    for k in keys:
        for kk in (k, k.upper(), k.lower()):
            if kk in row:
                try:
                    return float(row[kk])
                except (TypeError, ValueError):
                    pass
    return None


def _point_polygon(lon: float, lat: float, buffer_m: float) -> dict:
    """점을 한 변 ~2*buffer_m 인 정사각 폴리곤(GeoJSON, WGS84)으로 버퍼."""
    dlat = buffer_m / 111_000.0
    dlon = buffer_m / (111_000.0 * math.cos(math.radians(lat)))
    ring = [[lon - dlon, lat - dlat], [lon + dlon, lat - dlat],
            [lon + dlon, lat + dlat], [lon - dlon, lat + dlat], [lon - dlon, lat - dlat]]
    return {"type": "Polygon", "coordinates": [ring]}


def construction_events_from_rows(
    rows_: list[dict], *,
    lon_fields=("경도", "LON", "LNG", "X", "XCODE", "GRS80_LONG"),
    lat_fields=("위도", "LAT", "Y", "YCODE", "GRS80_LAT"),
    start_fields=("공사시작일", "STARTDATE", "BEGIN_DE"),
    end_fields=("공사종료일", "ENDDATE", "END_DE"),
    buffer_m: float = 25.0,
    source: str = "서울열린데이터광장(도로굴착)",
) -> list[DynamicEvent]:
    """서울 도로굴착 row → DynamicEvent(construction). 좌표는 WGS84 가정.

    실데이터 필드명/좌표계는 데이터셋마다 다르므로 필드 후보를 인자로 조정한다.
    (좌표가 TM 등이면 호출부에서 WGS84로 변환해 넣을 것.)
    """
    out = []
    for r in rows_:
        lon = _num(r, *lon_fields)
        lat = _num(r, *lat_fields)
        if lon is None or lat is None:
            continue
        out.append(DynamicEvent(
            event_type=EventType.construction,
            polygon=_point_polygon(lon, lat, buffer_m),
            start=_date(r, start_fields) or _FAR_PAST,
            end=_date(r, end_fields) or _FAR_FUTURE, source=source))
    return out


def fountains_from_rows(rows_: list[dict], *,
                        lon_fields=("경도", "LON", "X"), lat_fields=("위도", "LAT", "Y"),
                        name_fields=("시설명", "NAME", "PLACE")) -> list[POI]:
    """서울 아리수 음수대 row → POI(water_fountain)."""
    out = []
    for r in rows_:
        lon = _num(r, *lon_fields)
        lat = _num(r, *lat_fields)
        if lon is None or lat is None:
            continue
        name = next((str(r[k]) for k in name_fields if k in r and r[k]), "음수대")
        out.append(POI(poi_type=POIType.water_fountain, lat=lat, lon=lon, name=name, open_now=None))
    return out


def _date(row, keys):
    for k in keys:
        v = row.get(k) or row.get(k.upper())
        if v:
            s = str(v).strip().replace(".", "-").replace("/", "-")
            for fmt in ("%Y-%m-%d", "%Y%m%d"):
                token = s[:10] if "-" in s else s[:8]
                try:
                    return datetime.strptime(token, fmt).replace(tzinfo=SEOUL)
                except ValueError:
                    continue
    return None


def fetch_construction_events(service: str | None = None, **fields) -> list[DynamicEvent]:
    """도로굴착 서비스명(없으면 .env SEOUL_ROADDIG_SERVICE)으로 실 이벤트 수집."""
    service = service or config.get_key("SEOUL_ROADDIG_SERVICE")
    return construction_events_from_rows(rows(service), **fields) if service else []


def fetch_fountains(service: str | None = None, **fields) -> list[POI]:
    service = service or config.get_key("SEOUL_FOUNTAIN_SERVICE")
    return fountains_from_rows(rows(service), **fields) if service else []


__all__ = ["rows", "construction_events_from_rows", "fountains_from_rows",
           "fetch_construction_events", "fetch_fountains"]
