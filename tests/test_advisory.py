"""산책 게이트(walk_advisory) 검증 — 비 오면 무조건 막고, 아니면 확률·위험지수 순."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from engine.risk import walk_advisory
from engine.schemas import EnvObservation, RiskParams, Season

SEOUL = ZoneInfo("Asia/Seoul")


def _env(**over):
    base = dict(timestamp=datetime(2026, 7, 8, 15, 0, tzinfo=SEOUL), lat=37.5, lon=127.1,
                air_temp_c=22.0, humidity_pct=50.0, wind_ms=1.0, uv_index=2.0,
                pm10=20.0, pm25=8.0, road_surface_temp_c=24.0, season=Season.summer)
    base.update(over)
    return EnvObservation(**base)


def test_rain_now_hard_blocks_even_if_weather_mild():
    """비가 오면 열/미세먼지가 아무리 좋아도 stop(하드 게이트)."""
    adv = walk_advisory(_env(precip_type_code=1, precip_mm=2.5))
    assert adv.status == "stop" and adv.rain is True
    assert "비" in adv.reason


def test_snow_and_shower_also_block():
    for pty in (2, 3, 4):
        assert walk_advisory(_env(precip_type_code=pty)).status == "stop"


def test_precip_mm_positive_blocks_even_if_pty_zero():
    assert walk_advisory(_env(precip_type_code=0, precip_mm=1.2)).status == "stop"


def test_high_precip_probability_is_caution():
    adv = walk_advisory(_env(precip_prob_pct=70.0))
    assert adv.status == "caution" and adv.rain is False
    assert "70" in adv.reason


def test_clear_and_low_risk_is_go():
    adv = walk_advisory(_env(precip_prob_pct=10.0))
    assert adv.status == "go"


def test_clear_but_dangerous_heat_blocks_via_risk():
    """비는 안 와도 노면 과열(하드룰 red) → stop."""
    hot = _env(air_temp_c=36.0, humidity_pct=70.0, road_surface_temp_c=63.0,
               uv_index=9.0, pm10=40.0, pm25=20.0, precip_prob_pct=10.0)
    adv = walk_advisory(hot, params=RiskParams())
    assert adv.status == "stop" and adv.rain is False


def test_determinism():
    e = _env(precip_prob_pct=70.0)
    assert walk_advisory(e).model_dump() == walk_advisory(e).model_dump()
