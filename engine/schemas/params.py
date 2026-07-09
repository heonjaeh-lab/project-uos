"""파라미터 주입 규약(M5 대비 — 이번 범위 설계의 핵심).

위험 임계값·비용 가중치를 **코드에 하드코딩하지 않고 주입**한다. M2(위험지수)·
M3(라우팅) 함수는 반드시 이 params 객체를 인자로 받아야 한다(전역 상수 금지).

나중에 M5(개인화)는 `DogProfile → RiskParams/CostParams`를 만드는 함수만 추가하면
되며, 여기서 정한 **필드 이름·기본값 계약**은 그대로 유지된다(값만 교체 가능).
초기값은 문헌/기획서 기반 잠정값이며 실측·체감 피드백으로 보정한다.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RiskParams(BaseModel):
    """위험지수 가중치·신호등 임계값(0~100 점수 기준)."""

    heat_weight: float = Field(0.35, description="열지수(기온+습도) 기여 가중")
    surface_weight: float = Field(0.30, description="노면온도(발바닥 화상) 기여 가중")
    uv_weight: float = Field(0.15, description="자외선 기여 가중")
    pm_weight: float = Field(0.20, description="미세먼지 기여 가중")
    yellow_threshold: float = Field(40.0, description="노랑 경계 점수(0~100)")
    red_threshold: float = Field(70.0, description="빨강 경계 점수(0~100)")
    heat_offset_c: float = Field(
        0.0,
        description="개인화 온도 민감도 오프셋(℃). 양수면 더 낮은 기온에서 위험 상승(민감견).",
    )
    cold_offset_c: float = Field(
        0.0,
        description="개인화 온도 민감도 오프셋(℃). 양수면 더 높은(덜 추운) 기온에서 위험 상승(민감견).",
    )
    # TODO: 실측/체감 피드백으로 보정


class CostParams(BaseModel):
    """라우팅 비용함수 가중치·안전 게이트."""

    shade_bonus: float = Field(0.4, description="그늘 비율만큼 비용 할인 계수")
    hazard_penalty: float = Field(1.5, description="위험요소 페널티")
    construction_penalty: float = Field(5.0, description="공사 구간 페널티")
    assembly_penalty: float = Field(5.0, description="집회 구간 페널티")
    traffic_penalty: float = Field(1.2, description="교통 페널티")
    hard_block_level: str = Field(
        "red", description="이 위험등급 엣지는 그래프에서 제외(안전 게이트)"
    )


class DefaultParams:
    """주입 기본값 묶음. M5 미구현 동안 M2·M3가 이 기본값을 인자로 받는다.

    사용 예: `score = compute_risk(env, params=DefaultParams.risk)`.
    M5 도입 후에는 `DogProfile`에서 만든 `RiskParams`를 대신 넘기면 된다.
    """

    risk = RiskParams()
    cost = CostParams()


__all__ = ["RiskParams", "CostParams", "DefaultParams"]
