"""견종별 신체 특성 테이블(잠정값 — TODO 실측 보정).

한국에서 흔한 반려견 견종의 체급(size_class)·단두종 여부·더위/추위 민감 계수를
담는다. `profile_params.profile_to_risk_params`가 `breed`만 있고 size/brachy가
명시되지 않았을 때 이 테이블로 폴백한다.

heat_bias/cold_bias는 `RiskParams.heat_offset_c`/`cold_offset_c`에 가산되는 견종
고유 보정값(℃ 단위 감각)이다. 문헌·경험칙 기반 **잠정값**이며 실측/체감 피드백으로
반드시 보정해야 한다(TODO). 결정론(순수 데이터·룩업)이며 난수·IO 없음.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BreedTraits:
    """견종 고유 특성. 값은 모두 잠정(TODO: 실측 보정)."""

    size_class: str  # {"toy","small","medium","large"}
    brachycephalic: bool
    heat_bias: float  # ℃ 가산(양수=더위에 더 민감) — TODO 실측 보정
    cold_bias: float  # ℃ 가산(양수=추위에 더 민감, 음수=추위에 강함) — TODO 실측 보정


# ---------------------------------------------------------------------------
# 견종 특성표(잠정값) — 한국에서 흔한 견종 위주. 이중모피(더블코트)는 더위엔 약하고
# 추위엔 강한 경향, 단두종은 열사병 고위험, 초소형견은 저체온에 취약하다는 통념을
# 계수로 옮겼다. TODO: 실측/체감 피드백으로 보정.
# ---------------------------------------------------------------------------
BREED_TRAITS: dict[str, BreedTraits] = {
    "말티즈": BreedTraits("toy", False, 0.5, 1.0),
    "푸들": BreedTraits("small", False, 0.5, 0.5),
    "포메라니안": BreedTraits("toy", False, 1.0, -1.0),  # 더블코트: 더위 취약·추위 강함
    "치와와": BreedTraits("toy", False, 0.5, 1.5),  # 초소형·단모: 저체온 고위험
    "시츄": BreedTraits("small", True, 1.5, 0.5),  # 단두종
    "요크셔테리어": BreedTraits("toy", False, 0.5, 1.0),
    "비숑프리제": BreedTraits("small", False, 0.5, 0.5),
    "닥스훈트": BreedTraits("small", False, 0.0, 1.0),  # 단모+짧은 다리(지면 근접)
    "페키니즈": BreedTraits("toy", True, 1.5, 0.5),  # 단두종
    "파피용": BreedTraits("toy", False, 0.5, 1.0),
    "진돗개": BreedTraits("medium", False, 0.0, -1.0),  # 토종, 추위 강함
    "시바견": BreedTraits("small", False, 0.0, -0.5),
    "웰시코기": BreedTraits("small", False, 0.5, 0.0),
    "보더콜리": BreedTraits("medium", False, 1.0, -0.5),  # 더블코트·활동량 高
    "비글": BreedTraits("medium", False, 0.0, 0.0),
    "코커스패니얼": BreedTraits("medium", False, 0.5, 0.0),
    "슈나우저": BreedTraits("small", False, 0.0, 0.5),
    "프렌치불독": BreedTraits("medium", True, 2.5, 0.0),  # 단두종, 열사병 최고위험군
    "불독": BreedTraits("medium", True, 2.5, 0.0),  # 단두종
    "퍼그": BreedTraits("toy", True, 2.0, 0.5),  # 단두종
    "복서": BreedTraits("medium", True, 1.5, 0.0),  # 준단두종
    "시베리안허스키": BreedTraits("large", False, 1.5, -2.0),  # 극지견, 더위 취약·추위 매우 강함
    "사모예드": BreedTraits("large", False, 1.5, -2.0),  # 극지견
    "골든리트리버": BreedTraits("large", False, 0.5, -0.5),
    "래브라도리트리버": BreedTraits("large", False, 0.5, -0.5),
    "저먼셰퍼드": BreedTraits("large", False, 0.5, -0.5),
    "도베르만": BreedTraits("large", False, 0.0, 1.0),  # 단모, 추위엔 약함
    "로트와일러": BreedTraits("large", False, 0.0, -0.5),
    "믹스": BreedTraits("medium", False, 0.0, 0.0),  # 믹스/기타 — 중립값
}


def _norm(s: str) -> str:
    """공백/대소문자/구두점 무관 비교를 위한 정규화(영숫자·한글만 남김)."""
    return "".join(ch for ch in s.strip().lower() if ch.isalnum())


# 별칭(영문·줄임말·표기 변형) → 표준(한글) 견종 키. normalize_breed가 이 표와
# BREED_TRAITS 키를 함께 검색한다.
_ALIASES: dict[str, str] = {
    "maltese": "말티즈",
    "poodle": "푸들", "토이푸들": "푸들", "미니푸들": "푸들",
    "미니어처푸들": "푸들", "스탠다드푸들": "푸들", "토이 푸들": "푸들",
    "pomeranian": "포메라니안",
    "chihuahua": "치와와",
    "shihtzu": "시츄", "shih tzu": "시츄",
    "yorkshireterrier": "요크셔테리어", "요키": "요크셔테리어", "yorkie": "요크셔테리어",
    "bichonfrise": "비숑프리제", "비숑": "비숑프리제", "bichon": "비숑프리제",
    "dachshund": "닥스훈트", "닥스": "닥스훈트",
    "pekingese": "페키니즈",
    "papillon": "파피용",
    "jindo": "진돗개", "진도견": "진돗개", "jindodog": "진돗개",
    "shibainu": "시바견", "시바이누": "시바견", "shiba": "시바견",
    "corgi": "웰시코기", "코기": "웰시코기", "welshcorgi": "웰시코기",
    "bordercollie": "보더콜리",
    "beagle": "비글",
    "cockerspaniel": "코커스패니얼", "코카스패니얼": "코커스패니얼",
    "schnauzer": "슈나우저", "미니어처슈나우저": "슈나우저", "미니슈나우저": "슈나우저",
    "frenchbulldog": "프렌치불독", "프렌치불도그": "프렌치불독", "frenchie": "프렌치불독",
    "bulldog": "불독", "불도그": "불독", "잉글리시불독": "불독", "englishbulldog": "불독",
    "pug": "퍼그",
    "boxer": "복서",
    "siberianhusky": "시베리안허스키", "허스키": "시베리안허스키", "husky": "시베리안허스키",
    "samoyed": "사모예드",
    "goldenretriever": "골든리트리버", "골든": "골든리트리버", "golden": "골든리트리버",
    "labradorretriever": "래브라도리트리버", "라브라도": "래브라도리트리버",
    "래브라도": "래브라도리트리버", "labrador": "래브라도리트리버",
    "germanshepherd": "저먼셰퍼드", "셰퍼드": "저먼셰퍼드", "세퍼드": "저먼셰퍼드",
    "doberman": "도베르만", "도베르만핀셔": "도베르만",
    "rottweiler": "로트와일러",
    "mix": "믹스", "믹스견": "믹스", "잡종": "믹스", "기타": "믹스", "mixed": "믹스",
}

# 정규화 문자열 → 표준 키. 모듈 로드 시 1회 구축(결정론, 이후 순수 조회만).
_LOOKUP: dict[str, str] = {}
for _canon in BREED_TRAITS:
    _LOOKUP[_norm(_canon)] = _canon
for _alias, _canon in _ALIASES.items():
    _LOOKUP.setdefault(_norm(_alias), _canon)


def normalize_breed(name: str) -> str | None:
    """견종명 문자열(별칭/영문/공백·대소문자 무관) → 표준 한글 키. 못 찾으면 None."""
    if not name:
        return None
    return _LOOKUP.get(_norm(name))


def traits_for(breed: str) -> BreedTraits | None:
    """견종명(별칭 포함) → `BreedTraits`. 못 찾으면 None."""
    canon = normalize_breed(breed)
    return BREED_TRAITS.get(canon) if canon else None


__all__ = ["BreedTraits", "BREED_TRAITS", "normalize_breed", "traits_for"]
