"""산책 가능 여부 게이트(walk gate) — 강수 + 위험지수를 합쳐 go/caution/stop.

사용자가 "지금 나갈까?" 할 때의 최종 판단. **비/눈은 하드 스톱**(위험지수가 아무리
낮아도 막는다). 그다음 높은 강수확률은 주의, 그 외에는 위험지수(열/노면/자외선/미세먼지)
신호등을 따른다. 결정론 — 같은 입력이면 같은 판정.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from engine.risk.risk_index import RiskResult, compute_risk
from engine.schemas import EnvObservation, RiskLevel, RiskParams

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
) -> WalkAdvisory:
    """산책 가능 여부. 비/눈이면 무조건 stop, 아니면 강수확률·위험지수 순으로 판정."""
    # 1) 강수 하드 게이트: 지금 비/눈이 오면 막는다.
    pty = env.precip_type_code or 0
    mm = env.precip_mm or 0.0
    if pty != 0 or mm > 0:
        kind = PTY_KOR.get(pty, "비")
        amt = f" ({mm:.1f}mm)" if mm else ""
        return WalkAdvisory(status="stop", rain=True,
                            reason=f"지금 {kind}가 와요{amt}. 산책을 미뤄주세요.")

    # 2) 곧 비 예보(강수확률 높음) → 주의.
    pop = env.precip_prob_pct
    if pop is not None and pop >= CAUTION_POP_PCT:
        return WalkAdvisory(status="caution", rain=False,
                            reason=f"곧 비가 올 수 있어요(강수확률 {int(pop)}%). 짧게 다녀오세요.")

    # 3) 그 외엔 열/노면/자외선/미세먼지 위험지수 신호등을 따른다.
    if risk is None:
        risk = compute_risk(env, params or RiskParams(), missing=missing)
    if risk.level == RiskLevel.red:
        return WalkAdvisory(status="stop", rain=False, risk_level=risk.level,
                            reason=f"위험지수가 높아요({risk.dominant}). 지금은 실내를 권장해요.")
    if risk.level == RiskLevel.yellow:
        return WalkAdvisory(status="caution", rain=False, risk_level=risk.level,
                            reason=f"주의가 필요해요({risk.dominant}). 무리하지 말고 짧게.")
    return WalkAdvisory(status="go", rain=False, risk_level=risk.level,
                        reason="지금 산책하기 좋아요.")


__all__ = ["WalkAdvisory", "walk_advisory", "PTY_KOR"]
