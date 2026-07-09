"""GPS payload — 격자 선택(단위) + 실좌표 스키마(네트워크 게이트)."""
from __future__ import annotations

import os

import pytest

from engine.sources import weather


def test_hourly_risk_series_uses_gps_grid(monkeypatch):
    """lat/lon 지정 시 해당 격자(nx,ny)로 예보를 요청해야 한다(송파 기본 아님)."""
    captured = {}

    def fake_series(nx, ny, when=None, hours=12):
        captured["grid"] = (nx, ny)
        return []  # 시리즈 비면 out=[] → 격자 캡처만 검증

    monkeypatch.setattr(weather, "fetch_forecast_series", fake_series)
    monkeypatch.setattr(weather, "fetch_air_quality", lambda: {"pm10": 20.0, "pm25": 10.0})

    # 광화문 근처(송파와 다른 격자)
    weather.hourly_risk_series(hours=6, lat=37.5759, lon=126.9769)
    seoul_center_grid = weather.latlon_to_grid(37.5759, 126.9769)
    assert captured["grid"] == seoul_center_grid
    assert captured["grid"] != (weather.SONGPA_NX, weather.SONGPA_NY)


@pytest.mark.skipif(os.environ.get("RUN_LIVE") != "1",
                    reason="네트워크 라이브 스모크 — RUN_LIVE=1 일 때만")
def test_gps_map_payload_live_schema():
    """실좌표(서울시청 근처)로 실제 payload 생성 — map_data 스키마 키 검증."""
    from engine.sources.local_routing import gps_map_payload
    p = gps_map_payload(37.5663, 126.9779, dist_m=1200, target_m=1400, hours=6)
    for k in ("bbox", "gps", "origin", "dest", "routes", "hourly", "meta"):
        assert k in p, f"missing key {k}"
    assert len(p["bbox"]) == 4
    assert p["routes"], "no routes produced — schema check would be vacuous"
    for rt in p["routes"]:
        assert {"label", "shade", "distance_m", "est_time_min", "max_risk", "segs", "pois"} <= rt.keys()


@pytest.mark.skipif(os.environ.get("RUN_LIVE") != "1",
                    reason="네트워크 라이브 스모크 — RUN_LIVE=1 일 때만")
def test_gps_map_payload_live_dest_branch():
    """목적지 지정(dest) 분기 — 실좌표 A→B 경로 생성 + 스키마 검증."""
    from engine.sources.local_routing import gps_map_payload
    # 서울시청 → 북동쪽 약 1km 지점
    p = gps_map_payload(37.5663, 126.9779, dest=(37.5735, 126.9860),
                        dist_m=1200, hours=6)
    for k in ("bbox", "gps", "origin", "dest", "routes", "hourly", "meta"):
        assert k in p, f"missing key {k}"
    assert p["routes"], "no routes produced for dest branch"
    for rt in p["routes"]:
        assert {"label", "shade", "distance_m", "est_time_min", "max_risk", "segs", "pois"} <= rt.keys()
