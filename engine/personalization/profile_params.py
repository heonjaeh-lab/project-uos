"""`DogProfile` 필드 → `RiskParams` 개인화 오프셋 변환(M5 개인화의 첫 진입점).

순수 함수(난수·IO 없음) — 같은 입력이면 항상 같은 `RiskParams`를 낸다. 명시 인자
(breed/size/brachy/coat/age_years/conditions)가 있으면 그대로 쓰고, 없는 항목은
`breed_table`의 견종 테이블 값으로 폴백한다. 모든 계수는 문헌·경험칙 기반
**잠정값**이며 실측/체감 피드백으로 반드시 보정해야 한다(TODO 표시).

`compute_risk`/`_heat_norm`/`_cold_norm` 자체는 이 모듈을 모른다(계약: M2는
`RiskParams`만 받는다) — 개인화는 여기서 `RiskParams`를 만드는 것으로 끝난다.
"""

from __future__ import annotations

from engine.personalization.breed_table import traits_for
from engine.schemas.params import RiskParams

# ---------------------------------------------------------------------------
# heat_offset_c 산식 계수 (예, 상한 +8) — TODO: 실측/체감 피드백으로 보정.
# ---------------------------------------------------------------------------
_HEAT_BRACHY = 3.0
_HEAT_SIZE: dict[str, float] = {"toy": 2.0, "small": 1.0, "medium": 0.0, "large": -1.0}
_HEAT_COAT_LONG = 1.0
_HEAT_CONDITION_EACH = 2.0
_HEAT_CONDITIONS = {"obesity", "heart", "respiratory"}
_HEAT_CAP = 8.0

# ---------------------------------------------------------------------------
# cold_offset_c 산식 계수 (예, 상한 +6) — TODO: 실측/체감 피드백으로 보정.
# ---------------------------------------------------------------------------
_COLD_SIZE: dict[str, float] = {"toy": 3.0, "small": 2.0, "medium": 0.0, "large": -1.0}
_COLD_COAT_SHORT = 2.0
_COLD_AGE_EXTREME = 1.0  # age_years < 1 또는 > 8
_COLD_CAP = 6.0

_YOUNG_AGE_YEARS = 1.0
_OLD_AGE_YEARS = 8.0


def profile_to_risk_params(
    *,
    breed: str | None = None,
    size: str | None = None,
    brachy: bool | None = None,
    coat: str | None = None,
    age_years: float | None = None,
    conditions: list[str] | None = None,
    base: RiskParams | None = None,
) -> RiskParams:
    """견종/체급/단두종/털길이/나이/지병 → `heat_offset_c`·`cold_offset_c`를 얹은 RiskParams.

    명시 인자가 우선이며, 없는 항목은 `breed`(주어졌으면) 테이블 값으로 폴백한다.
    인자를 하나도 주지 않으면 offset 0(=`RiskParams()` 기본과 완전히 동일 — 회귀 안전).

    Args:
        breed: 견종명(별칭/영문 허용, `breed_table.normalize_breed` 참고).
        size: 체급 {"toy","small","medium","large"}. 없으면 breed 테이블 폴백.
        brachy: 단두종 여부. 없으면 breed 테이블 폴백(없으면 False).
        coat: 털 길이 {"short","medium","long"}(선택). 열/저체온 가중에만 반영.
        age_years: 나이(년, 선택). 1살 미만/8살 초과면 저체온 민감 가산.
        conditions: 지병 태그 목록(선택). obesity/heart/respiratory가 열 취약 가산.
        base: 병합 기준 RiskParams. 없으면 `RiskParams()` 기본 위에 offset만 얹는다.

    Returns:
        offset이 반영된 `RiskParams`(다른 필드는 base와 동일).
    """
    traits = traits_for(breed) if breed else None

    eff_size = size if size is not None else (traits.size_class if traits else None)
    eff_brachy = brachy if brachy is not None else bool(traits.brachycephalic) if traits else False
    breed_heat_bias = traits.heat_bias if traits else 0.0
    breed_cold_bias = traits.cold_bias if traits else 0.0

    heat_offset = 0.0
    if eff_brachy:
        heat_offset += _HEAT_BRACHY
    heat_offset += _HEAT_SIZE.get(eff_size, 0.0)
    if coat == "long":
        heat_offset += _HEAT_COAT_LONG
    cond_set = {c.strip().lower() for c in (conditions or [])}
    heat_offset += _HEAT_CONDITION_EACH * len(cond_set & _HEAT_CONDITIONS)
    heat_offset += breed_heat_bias
    heat_offset = min(_HEAT_CAP, heat_offset)  # 상한만 clamp(음수는 "덜 민감"으로 유지)

    cold_offset = 0.0
    cold_offset += _COLD_SIZE.get(eff_size, 0.0)
    if coat == "short":
        cold_offset += _COLD_COAT_SHORT
    if age_years is not None and (age_years < _YOUNG_AGE_YEARS or age_years > _OLD_AGE_YEARS):
        cold_offset += _COLD_AGE_EXTREME
    cold_offset += breed_cold_bias
    cold_offset = min(_COLD_CAP, cold_offset)  # 상한만 clamp

    src = base or RiskParams()
    return src.model_copy(update={"heat_offset_c": heat_offset, "cold_offset_c": cold_offset})


__all__ = ["profile_to_risk_params"]
