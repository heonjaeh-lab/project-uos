"""M2 위험지수 엔진 — 설명 가능한 결정론 공식.

반려견 산책 안전을 4대 환경 요소(열/노면/자외선/미세먼지)의 정규화·가중합으로
0~100 점수와 신호등(green/yellow/red)으로 판정한다. 왜 위험한지(요소별 기여)를
항상 함께 낸다. **난수·확률모델·런타임 LLM을 쓰지 않는다**(같은 입력 → 같은 출력).

설계 계약:
- 입력: `EnvObservation`(engine.schemas) + `RiskParams`(주입). `DogProfile`은 이번
  범위에서 무시(M5 개인화가 나중에 `DogProfile → RiskParams` 변환만 얹는다).
- 가중치·임계값은 **하드코딩하지 않고 `RiskParams`에서 주입**받는다. 계절별 가중
  조정은 주입된 base weight에 곱하는 배수(재정규화)로 표현한다.
- **노면온도는 입력 필드**(`road_surface_temp_c`)이며 추정(ML)하지 않는다.
- 결측(pm/surface)은 스키마상 필수 필드라 값으로 표현할 수 없으므로 `missing`
  인자로 신호받아 해당 요소를 중립(기여 0) 처리하고 `partial_data=True`.

상수 초기값은 문헌/경험칙 기반 **잠정값**이다 — 반드시 실측·체감 피드백으로 보정.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from pydantic import BaseModel, Field

from engine.schemas.common import RiskLevel, Season
from engine.schemas.environment import EnvObservation
from engine.schemas.params import RiskParams

# ---------------------------------------------------------------------------
# 정규화 임계 상수 — 각 요소를 "위험 없음 0 ~ 최대 위험 1"로 매핑하는 경계.
# 근거는 문헌/경험칙 기반 잠정값. 반드시 데이터로 보정할 것.
# ---------------------------------------------------------------------------

# 열 스트레스: 체감온도 = 기온 + 0.1*습도(정식 heat index 대신 경량 근사).
# 24℃ 이하는 위험 0, 38℃(체감)에서 위험 1. 근거: 개는 헐떡임으로만 방열하므로
# 고온·고습에서 열사병 위험 급증(일반 반려견 열스트레스 통념).
# TODO: 데이터로 보정 (견종·체급별 실측 heat tolerance).
HEAT_APPARENT_HUMIDITY_COEF = 0.1
HEAT_LOW_C = 24.0
HEAT_HIGH_C = 38.0

# 저체온(겨울 모드): 0℃ 이하부터 위험, -15℃에서 위험 1. 소형·단모종이 더 취약하나
# 그 보정은 M5(개인화)에서 반영. 근거: 저온 노출 시 소형견 저체온 위험 통념.
# TODO: 데이터로 보정.
COLD_HIGH_C = 0.0  # 이 온도 이하부터 위험 시작
COLD_LOW_C = -15.0  # 이 온도에서 위험 1

# 노면온도(발바닥 화상): 아스팔트 표면온도 경험칙. ~43℃부터 불편, ~52℃ 5초 접촉 시
# 화상 위험, 60℃+ 매우 위험. 43℃=위험 0, 60℃=위험 1로 정규화.
# 근거: 반려견 산책 안전에서 자주 인용되는 아스팔트 표면온도 경험칙.
# TODO: 데이터로 보정 (노면 재질·직사광 노출별 실측).
SURFACE_LOW_C = 43.0
SURFACE_HIGH_C = 60.0

# 자외선(WHO UV Index): 0~2 낮음 … 11+ 위험. 11로 나눠 0~1 정규화.
# 근거: WHO UV Index 구간. TODO: 데이터로 보정.
UV_MAX = 11.0

# 미세먼지(호흡기): PM2.5 76+ 매우나쁨, PM10은 그 2배 스케일. 더 나쁜 쪽 채택.
# 근거: 국내 대기질 등급(에어코리아) 통용 경계. TODO: 데이터로 보정.
PM25_MAX = 75.0
PM10_MAX = 150.0

# ---------------------------------------------------------------------------
# 하드 세이프티 임계 — 단일 요소가 극단이면 가중합과 무관하게 즉시 red로 승격.
# "평균이 낮아 위험이 희석되는" 문제를 막는다. 근거: 위 정규화 근거의 극단 구간.
# TODO: 데이터로 보정.
# ---------------------------------------------------------------------------
HARD_SURFACE_C = 60.0  # 노면 60℃+ → 화상 임박
HARD_PM25 = 76.0  # PM2.5 76+ → 매우나쁨
HARD_PM10 = 151.0  # PM10 151+ → 매우나쁨
HARD_UV = 11.0  # UV 11+ → 위험

# ---------------------------------------------------------------------------
# 계절별 가중 조정 배수 — 주입된 base weight(RiskParams)에 곱한 뒤 sum=1로 재정규화.
# base weight 자체는 주입값을 존중하고, "계절 모드"는 배수 공식으로만 표현한다.
#  - summer : 열·노면·자외선이 지배적 위해요인 → 상향(재정규화로 pm 상대 비중 하락).
#  - shoulder(간절기): 중립(1.0).
#  - winter : heat 슬롯을 저체온(cold)으로 대체. 노면(빙판)·자외선 위험은 라우팅(M3)
#             에서 회피하므로 위험지수에선 하향, 저체온·미세먼지 중심.
# 근거: 계절별 반려견 위해요인 통념(여름 열사병/화상, 겨울 저체온). TODO: 데이터로 보정.
# ---------------------------------------------------------------------------
SEASON_WEIGHT_MULT: dict[Season, dict[str, float]] = {
    Season.summer: {"heat": 1.15, "surface": 1.15, "uv": 1.15, "pm": 1.0},
    Season.shoulder: {"heat": 1.0, "surface": 1.0, "uv": 1.0, "pm": 1.0},
    Season.winter: {"heat": 1.0, "surface": 0.3, "uv": 0.3, "pm": 1.0},
}

# 요소 고정 순서 — dominant 산정의 결정론 tie-break, components 키 순서에 사용.
FACTOR_ORDER: tuple[str, ...] = ("heat", "surface", "uv", "pm")

# 출력 반올림 자리수(표시용). 등급 판정은 반올림 전 값으로 해 경계 흔들림 방지.
_SCORE_NDIGITS = 2
_COMPONENT_NDIGITS = 4


class RiskResult(BaseModel):
    """위험지수 산출 결과(설명 가능). 같은 입력이면 항상 동일하다."""

    score: float = Field(..., ge=0.0, le=100.0, description="위험지수 0~100")
    level: RiskLevel = Field(..., description="신호등 green|yellow|red")
    components: dict[str, float] = Field(
        ...,
        description=(
            "요소별 정규화 위험 0~1 {heat,surface,uv,pm}. "
            "겨울 모드에선 heat 슬롯이 저체온(cold) 기여를 담는다."
        ),
    )
    dominant: str = Field(..., description="가장 크게 기여한 요소(heat|surface|uv|pm)")
    recommended_windows: list[tuple[int, int]] | None = Field(
        None,
        description="권장 산책 시간대[(시작시, 끝시)…]. 예보 미제공 시 None",
    )
    partial_data: bool = Field(
        False, description="일부 요소 결측(중립 처리)이면 True"
    )
    triggered_hard_rules: list[str] = Field(
        default_factory=list,
        description="발동한 하드 세이프티 규칙 목록(설명용). 없으면 빈 리스트",
    )


# ---------------------------------------------------------------------------
# 정규화 헬퍼 (순수 함수)
# ---------------------------------------------------------------------------


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """[lo, hi]로 자른다."""
    return max(lo, min(hi, x))


def _heat_norm(air_temp_c: float, humidity_pct: float) -> float:
    """열 스트레스 정규화(기온+습도 체감 근사)."""
    apparent = air_temp_c + HEAT_APPARENT_HUMIDITY_COEF * humidity_pct
    return _clamp((apparent - HEAT_LOW_C) / (HEAT_HIGH_C - HEAT_LOW_C))


def _cold_norm(air_temp_c: float) -> float:
    """저체온 정규화(겨울 모드, heat 대체)."""
    return _clamp((COLD_HIGH_C - air_temp_c) / (COLD_HIGH_C - COLD_LOW_C))


def _surface_norm(road_surface_temp_c: float) -> float:
    """노면온도(발바닥 화상) 정규화."""
    return _clamp((road_surface_temp_c - SURFACE_LOW_C) / (SURFACE_HIGH_C - SURFACE_LOW_C))


def _uv_norm(uv_index: float) -> float:
    """자외선 정규화(WHO UV Index)."""
    return _clamp(uv_index / UV_MAX)


def _pm_norm(pm25: float, pm10: float) -> float:
    """미세먼지 정규화 — PM2.5/PM10 중 더 나쁜 쪽."""
    pm25_n = _clamp(pm25 / PM25_MAX)
    pm10_n = _clamp(pm10 / PM10_MAX)
    return max(pm25_n, pm10_n)


def _effective_weights(params: RiskParams, season: Season) -> dict[str, float]:
    """주입 base weight × 계절 배수 → sum=1 재정규화한 유효 가중치.

    base weight는 항상 `RiskParams`에서 온다(전역 상수 금지). 계절 모드는 배수로만
    개입한다. 합이 0이면(비정상) 균등 가중으로 폴백한다.
    """
    base = {
        "heat": params.heat_weight,
        "surface": params.surface_weight,
        "uv": params.uv_weight,
        "pm": params.pm_weight,
    }
    mult = SEASON_WEIGHT_MULT.get(season, SEASON_WEIGHT_MULT[Season.shoulder])
    raw = {k: base[k] * mult[k] for k in FACTOR_ORDER}
    total = sum(raw.values())
    if total <= 0.0:
        n = len(FACTOR_ORDER)
        return {k: 1.0 / n for k in FACTOR_ORDER}
    return {k: raw[k] / total for k in FACTOR_ORDER}


def classify_level(score: float, params: RiskParams) -> RiskLevel:
    """점수 → 신호등. 임계값은 주입된 `RiskParams`에서만 온다.

    라우팅(M3)·게임화 안전게이트(M6)가 이 함수를 공유하도록 명시 노출한다.
    """
    if score >= params.red_threshold:
        return RiskLevel.red
    if score >= params.yellow_threshold:
        return RiskLevel.yellow
    return RiskLevel.green


# ---------------------------------------------------------------------------
# 메인 진입점
# ---------------------------------------------------------------------------


def compute_risk(
    env: EnvObservation,
    params: RiskParams,
    *,
    missing: Iterable[str] | None = None,
    forecast: Sequence[EnvObservation] | None = None,
) -> RiskResult:
    """환경 관측 → 위험지수 결과(결정론).

    Args:
        env: 환경 관측(노면온도 포함, 추정 없이 입력값 사용).
        params: 주입 파라미터(가중치·임계값). 하드코딩 금지 계약의 핵심.
        missing: 결측 신호 집합. `{"pm"}`이면 미세먼지 결측 → pm 기여 0 + partial_data
            True + pm 하드규칙 스킵. `{"surface"}`이면 노면온도 결측 → 동일 처리.
            (스키마상 pm/surface는 필수 필드라 값으로 결측을 표현할 수 없어 신호로 받음.)
        forecast: (선택) 시간대별 예보. 주면 권장 산책 시간대를 채운다. 없으면 None.

    Returns:
        `RiskResult` — 같은 입력이면 항상 동일(난수 없음).
    """
    missing_set = {m.strip().lower() for m in (missing or [])}
    pm_missing = "pm" in missing_set or "pm25" in missing_set or "pm10" in missing_set
    surface_missing = "surface" in missing_set or "road_surface_temp_c" in missing_set
    partial_data = pm_missing or surface_missing

    # 1) 4대 요소 정규화(0~1). heat 슬롯은 계절에 따라 열 스트레스/저체온.
    if env.season == Season.winter:
        heat_component = _cold_norm(env.air_temp_c)
    else:
        heat_component = _heat_norm(env.air_temp_c, env.humidity_pct)

    surface_component = 0.0 if surface_missing else _surface_norm(env.road_surface_temp_c)
    uv_component = _uv_norm(env.uv_index)
    pm_component = 0.0 if pm_missing else _pm_norm(env.pm25, env.pm10)

    components = {
        "heat": heat_component,
        "surface": surface_component,
        "uv": uv_component,
        "pm": pm_component,
    }

    # 2) 가중합 → 점수(0~100). 유효 가중치는 주입값×계절배수(재정규화).
    weights = _effective_weights(params, env.season)
    contributions = {k: weights[k] * components[k] for k in FACTOR_ORDER}
    raw_score = 100.0 * sum(contributions.values())

    # 3) 등급 판정(반올림 전 raw_score로 경계 안정).
    level = classify_level(raw_score, params)

    # 4) dominant — 기여도(가중치×정규화값) 최대 요소. 고정 순서로 결정론 tie-break.
    dominant = max(FACTOR_ORDER, key=lambda k: (contributions[k], -FACTOR_ORDER.index(k)))

    # 5) 하드 세이프티 규칙 — 단일 극단이면 가중합과 무관하게 red 승격.
    #    결측 요소는 신뢰 불가 → 해당 요소의 하드규칙을 발동하지 않는다.
    triggered: list[str] = []
    hard_factor: str | None = None
    if not surface_missing and env.road_surface_temp_c >= HARD_SURFACE_C:
        triggered.append(f"surface>={HARD_SURFACE_C:g}C")
        hard_factor = "surface"
    if not pm_missing and (env.pm25 >= HARD_PM25 or env.pm10 >= HARD_PM10):
        triggered.append("pm(very_bad)")
        hard_factor = hard_factor or "pm"
    if env.uv_index >= HARD_UV:
        triggered.append(f"uv>={HARD_UV:g}")
        hard_factor = hard_factor or "uv"

    if triggered:
        level = RiskLevel.red
        # 하드 규칙이 발동했으면 dominant를 그 요소로 맞춰 설명 일관성 확보.
        if hard_factor is not None:
            dominant = hard_factor

    # 6) 권장 산책 시간대(예보가 있을 때만).
    recommended_windows = None
    if forecast is not None:
        recommended_windows = recommend_windows(forecast, params, missing=missing)

    return RiskResult(
        score=round(raw_score, _SCORE_NDIGITS),
        level=level,
        components={k: round(components[k], _COMPONENT_NDIGITS) for k in FACTOR_ORDER},
        dominant=dominant,
        recommended_windows=recommended_windows,
        partial_data=partial_data,
        triggered_hard_rules=triggered,
    )


def recommend_windows(
    forecast: Sequence[EnvObservation],
    params: RiskParams,
    *,
    missing: Iterable[str] | None = None,
) -> list[tuple[int, int]] | None:
    """시간대별 예보 → 권장 산책 시간대(연속 구간).

    각 시각의 score를 계산해 `level==green`인 연속 구간을 (시작시, 끝시) 리스트로
    반환한다(끝시 포함). green이 하나도 없으면 최저 score 시각 단일 구간을 준다.
    예보가 비면 None. 결정론(입력 순서·시각에만 의존, 난수 없음).
    """
    if not forecast:
        return None

    scored: list[tuple[int, float, RiskLevel]] = []
    for obs in forecast:
        r = compute_risk(obs, params, missing=missing)
        scored.append((obs.timestamp.hour, r.score, r.level))

    green_hours = [h for (h, _s, lvl) in scored if lvl == RiskLevel.green]
    if green_hours:
        return _contiguous_windows(sorted(green_hours))

    # green이 없으면 가장 안전한(최저 score) 시각 하나를 추천.
    best_hour = min(scored, key=lambda t: (t[1], t[0]))[0]
    return [(best_hour, best_hour)]


def _contiguous_windows(hours: list[int]) -> list[tuple[int, int]]:
    """정렬된 시각 리스트 → 연속 구간 (시작, 끝) 목록(끝 포함)."""
    windows: list[tuple[int, int]] = []
    start = prev = hours[0]
    for h in hours[1:]:
        if h == prev + 1:
            prev = h
            continue
        windows.append((start, prev))
        start = prev = h
    windows.append((start, prev))
    return windows


__all__ = [
    "RiskResult",
    "compute_risk",
    "classify_level",
    "recommend_windows",
]
