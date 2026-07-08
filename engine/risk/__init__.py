"""M2 위험지수 엔진 패키지.

결정론 공식으로 반려견 산책 위험지수(0~100)·신호등·요소별 기여·권장 시간대를
산출한다. 난수·확률모델·런타임 LLM을 쓰지 않는다. 가중치·임계값은 `RiskParams`
주입으로만 바꾼다(M5 개인화 대비).
"""

from __future__ import annotations

from engine.risk.advisory import WalkAdvisory, walk_advisory
from engine.risk.risk_index import (
    RiskResult,
    classify_level,
    compute_risk,
    recommend_windows,
)

__all__ = [
    "RiskResult",
    "compute_risk",
    "classify_level",
    "recommend_windows",
    "WalkAdvisory",
    "walk_advisory",
]
