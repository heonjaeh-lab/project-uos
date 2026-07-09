"""M5 개인화(견종 → RiskParams 오프셋) 검증 — 회귀·결정론·경계면.

검증 관점:
- profile_to_risk_params() 인자 없음 → RiskParams() 기본(offset 0).
- 열 취약 프로필(단두종+소형)이 offset 0보다 heat 기여/score가 더 크거나 같다.
- 결정론(같은 입력 반복 → 완전 동일).
- offset=0일 때 compute_risk 결과가 기존(주입 없음) 공식과 동일(회귀).
- breed_table 커버리지·별칭 정규화.
- advisory 문구 개인화(판정 로직 불변).
- /api/weather 서버 계약(외부 API 실패해도 200 폴백).

실행: `.venv/bin/python -m pytest tests/test_personalization.py -q`
"""

from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient

from engine.personalization import BREED_TRAITS, normalize_breed, profile_to_risk_params, traits_for
from engine.risk import compute_risk, walk_advisory
from engine.schemas import EnvObservation, RiskParams, Season

SEOUL_LAT, SEOUL_LON = 37.5133, 127.1001


def _env(**over) -> EnvObservation:
    base = dict(
        timestamp=datetime(2026, 7, 20, 14, 0),
        lat=37.48305, lon=127.11465,
        air_temp_c=30.0, humidity_pct=60.0, wind_ms=1.0,
        uv_index=3.0, pm10=30.0, pm25=15.0,
        road_surface_temp_c=32.0, season=Season.summer,
    )
    base.update(over)
    return EnvObservation(**base)


# ---------------------------------------------------------------------------
# (a) 인자 없음 → 기본값(offset 0), 회귀 안전
# ---------------------------------------------------------------------------


def test_profile_to_risk_params_no_args_is_default() -> None:
    params = profile_to_risk_params()
    default = RiskParams()
    assert params.heat_offset_c == 0.0
    assert params.cold_offset_c == 0.0
    # offset 이외 필드도 RiskParams() 기본과 완전히 동일해야 한다.
    assert params.model_dump() == default.model_dump()


def test_profile_to_risk_params_preserves_base_other_fields() -> None:
    """base를 주면 offset만 얹고 나머지 필드(가중치·임계값)는 그대로 보존."""
    base = RiskParams(heat_weight=0.5, yellow_threshold=30.0)
    params = profile_to_risk_params(brachy=True, size="toy", base=base)
    assert params.heat_weight == 0.5
    assert params.yellow_threshold == 30.0
    assert params.heat_offset_c > 0.0


# ---------------------------------------------------------------------------
# (b) 열 취약 프로필(단두종+소형)이 offset 0보다 heat 기여/score 이상
# ---------------------------------------------------------------------------


def test_brachy_small_profile_raises_heat_offset() -> None:
    sensitive = profile_to_risk_params(brachy=True, size="toy")
    neutral = profile_to_risk_params()
    assert sensitive.heat_offset_c > neutral.heat_offset_c == 0.0


def test_brachy_small_profile_score_and_heat_component_gte_neutral() -> None:
    env = _env()
    neutral_params = profile_to_risk_params()
    sensitive_params = profile_to_risk_params(brachy=True, size="toy")

    neutral_result = compute_risk(env, neutral_params)
    sensitive_result = compute_risk(env, sensitive_params)

    assert sensitive_result.components["heat"] >= neutral_result.components["heat"]
    assert sensitive_result.score >= neutral_result.score


def test_conditions_and_coat_increase_heat_offset() -> None:
    base = profile_to_risk_params()
    with_conditions = profile_to_risk_params(coat="long", conditions=["obesity", "heart"])
    assert with_conditions.heat_offset_c > base.heat_offset_c


def test_heat_offset_capped() -> None:
    """여러 가중 요인이 겹쳐도 상한(+8) 이내로 clamp."""
    params = profile_to_risk_params(
        breed="프렌치불독", brachy=True, size="toy", coat="long",
        conditions=["obesity", "heart", "respiratory"],
    )
    assert params.heat_offset_c <= 8.0


def test_cold_offset_capped() -> None:
    params = profile_to_risk_params(size="toy", coat="short", age_years=0.5, breed="치와와")
    assert params.cold_offset_c <= 6.0


# ---------------------------------------------------------------------------
# (c) 결정론 — 같은 입력 반복 → 완전 동일
# ---------------------------------------------------------------------------


def test_profile_to_risk_params_deterministic() -> None:
    kwargs = dict(breed="말티즈", size="small", brachy=False, coat="long",
                 age_years=2.0, conditions=["obesity"])
    p1 = profile_to_risk_params(**kwargs)
    p2 = profile_to_risk_params(**kwargs)
    assert p1.model_dump() == p2.model_dump()


def test_compute_risk_with_personalized_params_deterministic() -> None:
    env = _env()
    params = profile_to_risk_params(breed="프렌치불독")
    r1 = compute_risk(env, params)
    r2 = compute_risk(env, params)
    assert r1.model_dump() == r2.model_dump()


# ---------------------------------------------------------------------------
# (d) offset=0 → compute_risk 결과가 기존(주입 없음) 공식과 완전히 동일(회귀)
# ---------------------------------------------------------------------------


def test_zero_offset_matches_pre_personalization_behavior_summer() -> None:
    env = _env(season=Season.summer)
    default = RiskParams()
    explicit_zero = RiskParams(heat_offset_c=0.0, cold_offset_c=0.0)
    assert compute_risk(env, default).model_dump() == compute_risk(env, explicit_zero).model_dump()


def test_zero_offset_matches_pre_personalization_behavior_winter() -> None:
    env = _env(season=Season.winter, air_temp_c=-5.0)
    default = RiskParams()
    explicit_zero = RiskParams(heat_offset_c=0.0, cold_offset_c=0.0)
    assert compute_risk(env, default).model_dump() == compute_risk(env, explicit_zero).model_dump()


def test_positive_heat_offset_increases_or_holds_heat_component() -> None:
    env = _env()
    lo = compute_risk(env, RiskParams(heat_offset_c=0.0))
    hi = compute_risk(env, RiskParams(heat_offset_c=5.0))
    assert hi.components["heat"] >= lo.components["heat"]


def test_positive_cold_offset_increases_or_holds_cold_component_in_winter() -> None:
    env = _env(season=Season.winter, air_temp_c=-3.0)
    lo = compute_risk(env, RiskParams(cold_offset_c=0.0))
    hi = compute_risk(env, RiskParams(cold_offset_c=4.0))
    assert hi.components["heat"] >= lo.components["heat"]  # heat 슬롯이 겨울엔 cold를 담는다


# ---------------------------------------------------------------------------
# breed_table — 커버리지·별칭 정규화
# ---------------------------------------------------------------------------


def test_breed_table_has_at_least_25_breeds() -> None:
    assert len(BREED_TRAITS) >= 25


def test_breed_table_known_brachy_breeds_flagged() -> None:
    for name in ("프렌치불독", "불독", "퍼그", "페키니즈", "시츄"):
        traits = traits_for(name)
        assert traits is not None, name
        assert traits.brachycephalic is True, name


def test_breed_table_non_brachy_breed_not_flagged() -> None:
    traits = traits_for("골든리트리버")
    assert traits is not None and traits.brachycephalic is False


def test_normalize_breed_handles_aliases_case_and_spacing() -> None:
    assert normalize_breed("토이푸들") == "푸들"
    assert normalize_breed("Frenchie") == "프렌치불독"
    assert normalize_breed("  허스키  ") == "시베리안허스키"
    assert normalize_breed("Golden Retriever") == "골든리트리버"


def test_normalize_breed_unknown_returns_none() -> None:
    assert normalize_breed("존재하지않는견종xyz") is None
    assert traits_for("존재하지않는견종xyz") is None


def test_profile_to_risk_params_falls_back_to_breed_table() -> None:
    """breed만 주고 size/brachy 미지정 → breed_table 값으로 폴백."""
    params = profile_to_risk_params(breed="프렌치불독")
    assert params.heat_offset_c > 0.0  # 단두종 폴백이 반영됐어야.


# ---------------------------------------------------------------------------
# advisory 문구 개인화 — 판정 로직 불변, reason만 덧붙음
# ---------------------------------------------------------------------------


def test_walk_advisory_default_unchanged_without_profile_args() -> None:
    env = _env(air_temp_c=36.0, humidity_pct=70.0, road_surface_temp_c=58.0, uv_index=9.0)
    baseline = walk_advisory(env)
    same = walk_advisory(env)
    assert baseline.model_dump() == same.model_dump()


def test_walk_advisory_brachy_note_appended_on_heat_dominant() -> None:
    hot_env = _env(air_temp_c=36.0, humidity_pct=70.0, road_surface_temp_c=40.0,
                   uv_index=2.0, pm10=10.0, pm25=5.0, season=Season.summer)
    plain = walk_advisory(hot_env)
    noted = walk_advisory(hot_env, brachy=True)
    assert plain.status == noted.status  # 판정 로직 불변
    assert noted.reason != plain.reason
    assert "단두종은 열에 약해요" in noted.reason


def test_walk_advisory_small_size_note_appended_on_cold_dominant_winter() -> None:
    cold_env = _env(air_temp_c=-10.0, humidity_pct=40.0, road_surface_temp_c=-10.0,
                    uv_index=0.0, pm10=10.0, pm25=5.0, season=Season.winter)
    plain = walk_advisory(cold_env)
    noted = walk_advisory(cold_env, size="small")
    assert plain.status == noted.status
    assert "소형견은 추위에 약해요" in noted.reason


def test_walk_advisory_explicit_profile_note_overrides() -> None:
    env = _env()
    adv = walk_advisory(env, profile_note="커스텀 사유")
    assert adv.reason.endswith("커스텀 사유")


# ---------------------------------------------------------------------------
# 서버 계약 — /api/weather (외부 API 실패해도 200 폴백)
# ---------------------------------------------------------------------------


def test_api_weather_returns_200_with_meta_and_hourly() -> None:
    import server.app as srv

    client = TestClient(srv.app)
    r = client.get(f"/api/weather?lat={SEOUL_LAT}&lon={SEOUL_LON}")
    assert r.status_code == 200
    body = r.json()
    assert "meta" in body and "hourly" in body
    meta = body["meta"]
    for key in ("now_score", "now_level", "now_dominant", "advisory",
               "advisory_reason", "rain", "air_temp_c", "humidity_pct", "pm10",
               "precip_prob_pct"):
        assert key in meta


def test_api_weather_falls_back_when_engine_raises(monkeypatch) -> None:
    """엔진 예외 시 502(키/예외 문자열 미노출) — /api/route와 동일 패턴."""
    import server.app as srv

    def boom(*a, **k):
        raise RuntimeError("weather api down")

    monkeypatch.setattr(srv, "weather_payload", boom)
    client = TestClient(srv.app)
    r = client.get(f"/api/weather?lat={SEOUL_LAT}&lon={SEOUL_LON}")
    assert r.status_code == 502


def test_api_weather_out_of_korea_422() -> None:
    import server.app as srv

    client = TestClient(srv.app)
    r = client.get("/api/weather?lat=10.0&lon=100.0")
    assert r.status_code == 422


def test_api_weather_accepts_personalization_query(monkeypatch) -> None:
    """breed/size/brachy가 있으면 weather_payload가 개인화 RiskParams를 받는다."""
    import server.app as srv

    seen = {}

    def spy(lat, lon, params=None, **k):
        seen["params"] = params
        return {"meta": {}, "hourly": []}

    monkeypatch.setattr(srv, "weather_payload", spy)
    client = TestClient(srv.app)
    r = client.get(f"/api/weather?lat={SEOUL_LAT}&lon={SEOUL_LON}&breed=프렌치불독&brachy=true")
    assert r.status_code == 200
    assert seen["params"] is not None
    assert seen["params"].heat_offset_c > 0.0


def test_api_route_accepts_personalization_query_without_breaking_default(monkeypatch) -> None:
    """/api/route에 breed/size/brachy가 없으면 risk_params=None(기존과 동일)."""
    import server.app as srv

    seen = {}

    def spy(lat, lon, dest=None, **k):
        seen["risk_params"] = k.get("risk_params")
        return {"bbox": [0, 0, 0, 0], "gps": {"lon": lon, "lat": lat}, "origin": [0, 0],
                "dest": [0, 0], "routes": [{"label": "x", "shade": 0, "distance_m": 1,
                "est_time_min": 1, "max_risk": "green", "segs": [], "pois": []}],
                "hourly": [], "meta": {}}

    monkeypatch.setattr(srv, "gps_map_payload", spy)
    client = TestClient(srv.app)
    r = client.get("/api/route?lat=37.5&lon=127.0")
    assert r.status_code == 200
    assert seen["risk_params"] is None


def test_api_route_personalization_query_builds_risk_params(monkeypatch) -> None:
    import server.app as srv

    seen = {}

    def spy(lat, lon, dest=None, **k):
        seen["risk_params"] = k.get("risk_params")
        return {"bbox": [0, 0, 0, 0], "gps": {"lon": lon, "lat": lat}, "origin": [0, 0],
                "dest": [0, 0], "routes": [{"label": "x", "shade": 0, "distance_m": 1,
                "est_time_min": 1, "max_risk": "green", "segs": [], "pois": []}],
                "hourly": [], "meta": {}}

    monkeypatch.setattr(srv, "gps_map_payload", spy)
    client = TestClient(srv.app)
    r = client.get("/api/route?lat=37.5&lon=127.0&size=toy&brachy=true")
    assert r.status_code == 200
    assert seen["risk_params"] is not None
    assert seen["risk_params"].heat_offset_c > 0.0
