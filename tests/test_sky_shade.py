"""구름 반영 '실질 그늘'(effective shade) 테스트 — SKY clearness 보정 (M1 확장).

검증(설계: docs/superpowers/specs/2026-07-09-cloud-aware-shade-design.md):
- sky_clearness: 맑음(1)=1.0, 구름많음(3)=0.4, 흐림(4)=0.1, None/이상치=1.0(폴백=현행유지).
- effective_shade = 1-(1-geo)*clearness. 맑음이면 geo와 동일, 흐림이면 상승, 항상 [0,1].
- 결정론(같은 입력 같은 출력).
"""

from __future__ import annotations

import pytest

from engine.shade import effective_shade, sky_clearness


def test_sky_clearness_known_codes():
    assert sky_clearness(1) == 1.0   # 맑음
    assert sky_clearness(3) == 0.4   # 구름많음
    assert sky_clearness(4) == 0.1   # 흐림


@pytest.mark.parametrize("bad", [None, 0, 2, 5, -1, 99])
def test_sky_clearness_fallback_is_clear(bad):
    # 결측/미사용(2)/이상치 → 맑음(1.0)으로 폴백해 기존 동작 유지(회귀 없음)
    assert sky_clearness(bad) == 1.0


@pytest.mark.parametrize("geo", [0.0, 0.32, 0.78, 1.0])
def test_effective_equals_geometric_when_clear(geo):
    assert effective_shade(geo, 1.0) == pytest.approx(geo)


def test_effective_rises_when_overcast():
    # 기하 32% + 흐림(0.1) → 1-0.68*0.1 = 0.932
    assert effective_shade(0.32, 0.1) == pytest.approx(0.932)
    # 흐릴수록 실질 그늘은 기하 이상
    assert effective_shade(0.2, 0.1) >= 0.2
    assert effective_shade(0.5, 0.4) >= 0.5


@pytest.mark.parametrize("geo", [-0.5, 0.0, 0.5, 1.0, 1.5])
@pytest.mark.parametrize("c", [-0.5, 0.0, 0.4, 1.0, 1.5])
def test_effective_shade_bounded_0_1(geo, c):
    v = effective_shade(geo, c)
    assert 0.0 <= v <= 1.0


def test_effective_shade_deterministic():
    assert effective_shade(0.32, 0.4) == effective_shade(0.32, 0.4)
