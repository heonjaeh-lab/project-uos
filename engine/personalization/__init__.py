"""M5 개인화 진입점(범위 최소) — `DogProfile`/견종 → `RiskParams` 오프셋 변환.

M5(개인화) 전체는 별도 기획 중이라 이번 범위에서는 위험지수 온도 오프셋
(`heat_offset_c`/`cold_offset_c`)만 다룬다. 라우팅 비용(`CostParams`) 개인화는
포함하지 않는다(하드 세이프티 게이트는 견종 무관하게 그대로 유지).
"""

from __future__ import annotations

from engine.personalization.breed_table import BreedTraits, BREED_TRAITS, normalize_breed, traits_for
from engine.personalization.profile_params import profile_to_risk_params

__all__ = [
    "BreedTraits",
    "BREED_TRAITS",
    "normalize_breed",
    "traits_for",
    "profile_to_risk_params",
]
