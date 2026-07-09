"""구름(하늘상태 SKY) 반영 '실질 그늘' — 기하 그늘을 실제 일조로 보정 (M1 확장).

`engine/shade/shade.py` 의 기하 그늘(맑은 하늘 가정 건물 그림자 비율)에, 기상청
단기예보 하늘상태(SKY)로 얻은 '하늘 맑은 정도(clearness)'를 곱해 사용자가 체감하는
**실질 그늘**을 낸다. 흐릴수록 직사광이 없어 전 구간이 사실상 그늘 → 100% 에 근접.

순수 함수·결정론(ML·난수 없음). SKY 는 `EnvObservation.sky_code` 로 이미 수집된다.
"""

from __future__ import annotations

# 기상청 단기예보 하늘상태(SKY) → 하늘 맑은 정도(직사광 투과율 근사, 0~1).
#   1: 맑음 · 3: 구름많음 · 4: 흐림  (2 는 미사용 코드)
# 결측/미사용/이상치는 맑음(1.0)으로 폴백해 기존 동작(기하 그늘)을 유지한다(회귀 없음).
_SKY_CLEARNESS: dict[int, float] = {1: 1.0, 3: 0.4, 4: 0.1}


def sky_clearness(sky_code: int | None) -> float:
    """하늘상태 SKY 코드 → clearness(0~1). 결측/이상치 → 1.0(맑음 가정)."""
    return _SKY_CLEARNESS.get(sky_code, 1.0)


def effective_shade(geometric_shade: float, clearness: float) -> float:
    """기하 그늘 + 하늘 맑은 정도 → 실질 그늘(0~1).

    effective = 1 - (1 - geo) * clearness
    - clearness=1.0(맑음/결측)이면 effective == geometric (현행과 동일).
    - 흐릴수록(clearness↓) 직사광 노출↓ → effective↑ (전 구간 그늘 효과).
    입력이 범위를 벗어나도 [0,1] 로 클램프해 안전하게 반환한다.
    """
    geo = min(1.0, max(0.0, geometric_shade))
    c = min(1.0, max(0.0, clearness))
    return 1.0 - (1.0 - geo) * c


__all__ = ["sky_clearness", "effective_shade"]
