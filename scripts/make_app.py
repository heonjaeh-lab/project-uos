"""data/demo/map_data.json 의 엔진 산출 스냅샷을 앱의 데모 DATA로 재주입한다.

⚠️ 이 스크립트는 더 이상 앱 디자인(HTML/CSS/JS)을 **생성**하지 않는다.
`docs/app/index.html` 이 디자인 **원본(수기 편집)** 이며, 여기서는 그 안의
`const DATA=...;` **한 줄만** map_data.json 최신값으로 교체한다.
따라서 재실행해도 손으로 다듬은 디자인/로직을 덮어쓰지 않는다.
(과거엔 임베드된 템플릿으로 통째 생성해 수기 디자인을 클로버링했음 — 그 문제를 제거.)

API_BASE 는 프론트가 런타임에 자동 판별(localhost→로컬 서버, 그 외→Azure FQDN)하므로
빌드 시 주입하지 않는다.

사용: `.venv/bin/python scripts/make_app.py`
      (map_data.json 을 새로 구운 뒤 데모 데이터만 새로고침할 때)
"""
import json
import re

SRC = "data/demo/map_data.json"
CANON = "docs/app/index.html"                      # 디자인 원본 = 유일 정본(수기)
TARGETS = ["docs/app/index.html"]                  # 미러(조심해야댕.html)는 제거됨 — 정본 1개만 갱신

with open(SRC, encoding="utf-8") as f:
    data = json.load(f)
data_line = "const DATA=" + json.dumps(data, ensure_ascii=False) + ";"

with open(CANON, encoding="utf-8") as f:
    html = f.read()

# `const DATA=...;` (단일 라인)만 교체. 나머지 디자인/로직은 그대로 보존.
# 치환값에 함수를 써서 JSON 내 역슬래시·$ 등이 정규식 백참조로 오해석되지 않게 한다.
new_html, n = re.subn(r"^const DATA=.*;[ \t]*$", lambda _m: data_line, html,
                      count=1, flags=re.MULTILINE)
if n != 1:
    raise SystemExit(
        f"'const DATA=' 라인을 정확히 1개 찾지 못했습니다(발견 {n}개). "
        f"{CANON} 구조를 확인하세요."
    )

for path in TARGETS:
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_html)

print(
    f"refreshed DATA in: {', '.join(TARGETS)} "
    f"({len(new_html)} bytes, routes={len(data.get('routes', []))})"
)
