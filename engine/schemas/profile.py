"""반려견 프로필 스키마.

M5(개인화)가 나중에 `DogProfile → RiskParams/CostParams` 변환 함수를 얹는다.
이번 범위에서는 **필드만** 정의하고 어떤 로직(가중치 매핑 등)도 넣지 않는다.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class CoatLength(str, Enum):
    """털 길이."""

    short = "short"
    medium = "medium"
    long = "long"


class SizeClass(str, Enum):
    """체급 분류."""

    toy = "toy"
    small = "small"
    medium = "medium"
    large = "large"


class DogProfile(BaseModel):
    """반려견 프로필. M5 개인화의 입력이 되는 순수 데이터(로직 없음)."""

    breed: str = Field(..., description="견종명(예: 'poodle', '말티즈')")
    age_years: float = Field(..., ge=0.0, description="나이(년)")
    weight_kg: float = Field(..., gt=0.0, description="체중(kg)")
    coat_length: CoatLength = Field(..., description="털 길이 {short|medium|long}")
    brachycephalic: bool = Field(..., description="단두종 여부(열 취약)")
    size_class: SizeClass = Field(..., description="체급 {toy|small|medium|large}")
    conditions: list[str] = Field(
        default_factory=list,
        description="지병·주의사항 태그(예: 'patella', 'heart', 'obesity')",
    )


__all__ = ["CoatLength", "SizeClass", "DogProfile"]
