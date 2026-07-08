---
name: engine-qa
description: 조심해야댕 엔진의 pytest 검증과 모듈 경계면 교차 비교를 수행할 때 사용. mock fixtures 작성, 결정론(재현성) 검증, 경계면 shape/단위 대조, assertion 패턴을 담는다. qa-verifier 에이전트가 각 모듈 완성 직후 사용.
---

# engine-qa — 엔진 품질 검증

"돌아간다"가 아니라 "옳게 돌아간다"를 증거로 확인한다. 검증 스크립트를 **직접 실행**하고 출력을 근거로 판단한다.

## 검증의 3층
1. **단위(unit)**: 각 함수가 대표 입력에 대해 기대 출력을 내는가 (assertion).
2. **경계면(integration)**: 두 모듈이 주고받는 데이터의 shape·단위·의미가 일치하는가. ← **가장 중요, 버그가 여기 숨는다.**
3. **재현성(determinism)**: 같은 입력을 2회 실행 → 완전히 동일한 출력인가.

## 왜 경계면인가
각 모듈은 단독으론 통과해도, 한쪽이 낸 값을 다른 쪽이 오해하면 통합에서 깨진다. "존재 확인"이 아니라 **"생산자 출력 ↔ 소비자 기대"를 양쪽 코드를 함께 읽고 대조**한다.

조심해야댕의 핵심 경계면:
| 생산자 | 소비자 | 대조 포인트 |
|--------|--------|-----------|
| M1 그늘 `shade_ratio`(0~1) | M3 비용함수 | 범위·방향(그늘↑→비용↓) 맞는가 |
| M2 위험지수 `level` | M3 안전 게이트 | `red` 엣지가 실제로 hard-block 되는가 |
| M0 스키마 필드명/단위 | 전 모듈 | 실제 접근 필드명이 스키마와 일치하는가 |
| M3 경로 엣지 | M4 리라우팅 | 폴리곤 교차 판정·변경 diff가 정확한가 |

## pytest 컨벤션
- 파일: `tests/test_{module}.py`. 실행: `.venv/bin/python -m pytest -q`.
- fixtures는 `data/mock/`의 JSON을 로드하거나 `tests/conftest.py`에 정의.
- 경계면 테스트는 `tests/test_integration.py`에 모아, 생산자→소비자 실제 호출로 검증.

## 재현성 검증 패턴
```python
def test_determinism(...):
    r1 = compute(fixed_input)
    r2 = compute(fixed_input)
    assert r1 == r2   # 결정론 엔진: 완전 동일해야
```

## 경계면 테스트 예시 (위험지수 → 라우팅 게이트)
```python
def test_red_edge_is_hard_blocked(songpa_graph, red_env, default_params):
    # 특정 엣지에 red 유발 환경을 주입
    G = annotate_risk(songpa_graph, red_env, default_params)
    route = find_route(G, orig, dest, default_params)
    # red 엣지가 경로에 포함되지 않아야 (hard-block)
    assert not route_uses_red_edge(route, G)
```

## 리포트 형식 (`_workspace/qa_{module}.md`)
- 실행 명령 + 실제 출력 요약(통과 N / 실패 M).
- 발견 이슈: 무엇이·어디서·어떤 입력에서 깨지는가, 담당 에이전트 지목.
- 실패 시 로그 원문 인용. **통과를 가장하지 않는다.**

## 원칙
- 명백한 소규모 결함은 담당 builder에게 SendMessage로 알리고, 수정은 담당자가. QA는 재검증.
- 점진적으로: 모듈 완성 직후 즉시 검증. 전체 완성 후 몰아서 하지 않는다.
