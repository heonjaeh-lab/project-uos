"""M2 위험지수 엔진 검증 — 결정론·경계·하드규칙·결측.

QA 관점(risk-index SKILL 검증 섹션과 공유):
- 폭염 → red, dominant ∈ {heat, surface}
- 쾌적 → green
- 노면 60℃ → 하드 세이프티 규칙으로 red
- 미세먼지 결측 → partial_data=True, pm 기여 0
- 같은 입력 2회 → 동일 결과(결정론)

실행: `.venv/bin/python -m pytest tests/test_risk.py -q`
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from engine.risk import classify_level, compute_risk, recommend_windows
from engine.schemas import DefaultParams, EnvObservation, RiskLevel, RiskParams, Season

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_DIR = PROJECT_ROOT / "data" / "mock" / "risk_scenarios"


# ---------------------------------------------------------------------------
# fixture 로더
# ---------------------------------------------------------------------------


def _load_scenarios() -> list[dict]:
    files = sorted(SCENARIO_DIR.glob("*.json"))
    assert files, f"시나리오 fixture가 없다: {SCENARIO_DIR}"
    return [json.loads(p.read_text(encoding="utf-8")) for p in files]


SCENARIOS = _load_scenarios()


def _env(scn: dict) -> EnvObservation:
    return EnvObservation(**scn["env"])


def _run(scn: dict):
    return compute_risk(_env(scn), DefaultParams.risk, missing=scn.get("missing"))


# ---------------------------------------------------------------------------
# 데이터 주도 검증 — 각 fixture의 expect 블록을 그대로 확인
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("scn", SCENARIOS, ids=[s["name"] for s in SCENARIOS])
def test_scenario_expectations(scn: dict) -> None:
    result = _run(scn)
    expect = scn.get("expect", {})

    # 기본 불변식
    assert 0.0 <= result.score <= 100.0
    assert set(result.components) == {"heat", "surface", "uv", "pm"}
    assert all(0.0 <= v <= 1.0 for v in result.components.values())
    assert result.dominant in {"heat", "surface", "uv", "pm"}

    if "level" in expect:
        assert result.level.value == expect["level"], (
            f"{scn['name']}: level {result.level.value} != {expect['level']}"
        )
    if "dominant" in expect:
        assert result.dominant == expect["dominant"]
    if "dominant_in" in expect:
        assert result.dominant in expect["dominant_in"]
    if "partial_data" in expect:
        assert result.partial_data is expect["partial_data"]
    if expect.get("pm_component_zero"):
        assert result.components["pm"] == 0.0
    if expect.get("heat_component_positive"):
        assert result.components["heat"] > 0.0
    if "hard_rule_contains" in expect:
        token = expect["hard_rule_contains"]
        assert any(token in r for r in result.triggered_hard_rules)
    if "hard_rule_absent" in expect:
        token = expect["hard_rule_absent"]
        assert not any(token in r for r in result.triggered_hard_rules)


# ---------------------------------------------------------------------------
# SKILL 검증 시나리오 — 명시적 개별 테스트
# ---------------------------------------------------------------------------


def _scn(name: str) -> dict:
    for s in SCENARIOS:
        if s["name"] == name:
            return s
    raise AssertionError(f"fixture 없음: {name}")


def test_heatwave_is_red_dominated_by_heat_or_surface() -> None:
    result = _run(_scn("heatwave"))
    assert result.level == RiskLevel.red
    assert result.dominant in {"heat", "surface"}


def test_comfortable_is_green() -> None:
    result = _run(_scn("comfortable"))
    assert result.level == RiskLevel.green
    assert result.partial_data is False


def test_surface_60_triggers_hard_red_rule() -> None:
    scn = _scn("surface60")
    result = _run(scn)
    assert result.level == RiskLevel.red
    assert result.dominant == "surface"
    assert any("surface" in r for r in result.triggered_hard_rules)
    # 하드 규칙이 없었다면 가중합만으로는 red 미만이어야(=규칙이 승격의 원인).
    assert result.score < DefaultParams.risk.red_threshold


def test_pm_missing_sets_partial_data_and_neutralizes_pm() -> None:
    result = _run(_scn("pm_missing"))
    assert result.partial_data is True
    assert result.components["pm"] == 0.0
    # 결측 요소는 하드규칙을 발동시키지 않는다.
    assert not any("pm" in r for r in result.triggered_hard_rules)


def test_missing_pm_skips_hard_rule_even_with_extreme_placeholder() -> None:
    """PM 자리표시값이 하드 임계를 넘어도, 결측이면 red로 승격되면 안 된다."""
    env = EnvObservation(
        timestamp=datetime(2026, 7, 20, 12, 0),
        lat=37.48305,
        lon=127.11465,
        air_temp_c=20.0,
        humidity_pct=45.0,
        wind_ms=1.0,
        uv_index=2.0,
        pm10=300.0,  # 하드 임계 초과값이지만 결측 신호로 무시돼야 함
        pm25=200.0,
        road_surface_temp_c=25.0,
        season=Season.summer,
    )
    result = compute_risk(env, DefaultParams.risk, missing=["pm"])
    assert result.partial_data is True
    assert result.components["pm"] == 0.0
    assert not any("pm" in r for r in result.triggered_hard_rules)
    assert result.level != RiskLevel.red


# ---------------------------------------------------------------------------
# 하드 세이프티 규칙 (UV / PM)
# ---------------------------------------------------------------------------


def _base_env(**overrides) -> EnvObservation:
    fields = dict(
        timestamp=datetime(2026, 7, 20, 12, 0),
        lat=37.48305,
        lon=127.11465,
        air_temp_c=20.0,
        humidity_pct=45.0,
        wind_ms=1.0,
        uv_index=2.0,
        pm10=20.0,
        pm25=10.0,
        road_surface_temp_c=25.0,
        season=Season.summer,
    )
    fields.update(overrides)
    return EnvObservation(**fields)


def test_hard_rule_uv_extreme_forces_red() -> None:
    result = compute_risk(_base_env(uv_index=11.0), DefaultParams.risk)
    assert result.level == RiskLevel.red
    assert any("uv" in r for r in result.triggered_hard_rules)


def test_hard_rule_pm_very_bad_forces_red() -> None:
    result = compute_risk(_base_env(pm25=80.0), DefaultParams.risk)
    assert result.level == RiskLevel.red
    assert any("pm" in r for r in result.triggered_hard_rules)


# ---------------------------------------------------------------------------
# 결정론
# ---------------------------------------------------------------------------


def test_deterministic_same_input_same_output() -> None:
    scn = _scn("heatwave")
    r1 = compute_risk(_env(scn), DefaultParams.risk, missing=scn.get("missing"))
    r2 = compute_risk(_env(scn), DefaultParams.risk, missing=scn.get("missing"))
    assert r1.model_dump() == r2.model_dump()


def test_deterministic_across_all_scenarios() -> None:
    for scn in SCENARIOS:
        r1 = _run(scn)
        r2 = _run(scn)
        assert r1.model_dump() == r2.model_dump(), scn["name"]


# ---------------------------------------------------------------------------
# 파라미터 주입 — 하드코딩 금지 계약
# ---------------------------------------------------------------------------


def test_thresholds_are_injected_not_hardcoded() -> None:
    """임계값을 낮추면 같은 관측이라도 등급이 올라가야 한다(주입이 실제로 반영)."""
    env = _env(_scn("comfortable"))
    strict = RiskParams(yellow_threshold=1.0, red_threshold=3.0)
    lenient = RiskParams(yellow_threshold=95.0, red_threshold=99.0)
    assert compute_risk(env, strict).level == RiskLevel.red
    assert compute_risk(env, lenient).level == RiskLevel.green


def test_classify_level_boundaries() -> None:
    params = RiskParams(yellow_threshold=40.0, red_threshold=70.0)
    assert classify_level(39.999, params) == RiskLevel.green
    assert classify_level(40.0, params) == RiskLevel.yellow
    assert classify_level(69.999, params) == RiskLevel.yellow
    assert classify_level(70.0, params) == RiskLevel.red


# ---------------------------------------------------------------------------
# 권장 산책 시간대
# ---------------------------------------------------------------------------


def test_recommend_windows_picks_green_contiguous_runs() -> None:
    # 이른 아침 쾌적(green), 한낮 폭염(red) 예보 → 아침 연속 구간만 추천.
    forecast = [
        _base_env(timestamp=datetime(2026, 7, 20, 7, 0), air_temp_c=20.0, road_surface_temp_c=25.0, uv_index=1.0),
        _base_env(timestamp=datetime(2026, 7, 20, 8, 0), air_temp_c=21.0, road_surface_temp_c=27.0, uv_index=2.0),
        _base_env(timestamp=datetime(2026, 7, 20, 14, 0), air_temp_c=36.0, humidity_pct=70.0, road_surface_temp_c=58.0, uv_index=9.0),
    ]
    windows = recommend_windows(forecast, DefaultParams.risk)
    assert windows == [(7, 8)]


def test_recommend_windows_none_for_empty_forecast() -> None:
    assert recommend_windows([], DefaultParams.risk) is None
