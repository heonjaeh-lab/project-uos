"""산책 가능 여부 게이트(walk gate) — 강수 + 위험지수를 합쳐 go/caution/stop.

사용자가 "지금 나갈까?" 할 때의 최종 판단. **비/눈은 하드 스톱**(위험지수가 아무리
낮아도 막는다). 그다음 높은 강수확률은 주의, 그 외에는 위험지수(열/노면/자외선/미세먼지)
신호등을 따른다. 결정론 — 같은 입력이면 같은 판정.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from engine.risk.risk_index import RiskResult, compute_risk
from engine.schemas import EnvObservation, RiskLevel, RiskParams, Season

# PTY(강수형태) 코드 → 한글
PTY_KOR = {1: "비", 2: "비/눈", 3: "눈", 4: "소나기"}
CAUTION_POP_PCT = 60.0  # 이 이상 강수확률이면 주의


class WalkAdvisory(BaseModel):
    """산책 권고. status=stop이면 앱이 산책 시작을 막고 실내를 권한다."""

    status: Literal["go", "caution", "stop"] = Field(..., description="go=권장/caution=주의/stop=막음")
    rain: bool = Field(..., description="강수로 인한 판정인지")
    reason: str = Field(..., description="사용자에게 보여줄 사유")
    risk_level: RiskLevel | None = Field(None, description="참고: 열/미세먼지 위험 신호등")


def walk_advisory(
    env: EnvObservation,
    risk: RiskResult | None = None,
    *,
    params: RiskParams | None = None,
    missing=None,
    profile_note: str | None = None,
    brachy: bool = False,
    size: str | None = None,
) -> WalkAdvisory:
    """산책 가능 여부. 비/눈이면 무조건 stop, 아니면 강수확률·위험지수 순으로 판정.

    `profile_note`(또는 `brachy`/`size`)는 **판정 로직에는 전혀 영향을 주지 않고**
    reason 문자열 끝에 견종 사유만 덧붙이는 선택 기능이다(M5 개인화 문구 보강).
    인자를 하나도 주지 않으면 기존과 완전히 동일한 결과를 낸다(회귀 안전).
    """
    dominant: str | None = None

    # 1) 강수 하드 게이트: 지금 비/눈이 오면 막는다.
    pty = env.precip_type_code or 0
    mm = env.precip_mm or 0.0
    if pty != 0 or mm > 0:
        kind = PTY_KOR.get(pty, "비")
        amt = f" ({mm:.1f}mm)" if mm else ""
        result = WalkAdvisory(status="stop", rain=True,
                              reason=f"지금 {kind}가 와요{amt}. 산책을 미뤄주세요.")
        return _with_profile_note(result, env, dominant, profile_note=profile_note, brachy=brachy, size=size)

    # 2) 곧 비 예보(강수확률 높음) → 주의.
    pop = env.precip_prob_pct
    if pop is not None and pop >= CAUTION_POP_PCT:
        result = WalkAdvisory(status="caution", rain=False,
                              reason=f"곧 비가 올 수 있어요(강수확률 {int(pop)}%). 짧게 다녀오세요.")
        return _with_profile_note(result, env, dominant, profile_note=profile_note, brachy=brachy, size=size)

    # 3) 그 외엔 열/노면/자외선/미세먼지 위험지수 신호등을 따른다.
    if risk is None:
        risk = compute_risk(env, params or RiskParams(), missing=missing)
    dominant = risk.dominant
    if risk.level == RiskLevel.red:
        result = WalkAdvisory(status="stop", rain=False, risk_level=risk.level,
                              reason=f"위험지수가 높아요({risk.dominant}). 지금은 실내를 권장해요.")
    elif risk.level == RiskLevel.yellow:
        result = WalkAdvisory(status="caution", rain=False, risk_level=risk.level,
                              reason=f"주의가 필요해요({risk.dominant}). 무리하지 말고 짧게.")
    else:
        result = WalkAdvisory(status="go", rain=False, risk_level=risk.level,
                              reason="지금 산책하기 좋아요.")
    return _with_profile_note(result, env, dominant, profile_note=profile_note, brachy=brachy, size=size)


def _with_profile_note(
    advisory: WalkAdvisory,
    env: EnvObservation,
    dominant: str | None,
    *,
    profile_note: str | None,
    brachy: bool,
    size: str | None,
) -> WalkAdvisory:
    """reason 끝에 견종 사유를 덧붙인다(판정 자체는 불변). 인자가 없으면 그대로 반환.

    예: 단두종+더움(dominant=heat, 여름/간절기) → "단두종은 열에 약해요".
        소형+추움(dominant=heat 슬롯이 저체온을 담는 겨울) → "소형견은 추위에 약해요".
    """
    note = profile_note
    if note is None and dominant == "heat":
        if env.season == Season.winter and size in ("toy", "small"):
            note = "소형견은 추위에 약해요"
        elif env.season != Season.winter and brachy:
            note = "단두종은 열에 약해요"
    if not note:
        return advisory
    return advisory.model_copy(update={"reason": f"{advisory.reason} {note}"})


__all__ = ["WalkAdvisory", "walk_advisory", "PTY_KOR"]
