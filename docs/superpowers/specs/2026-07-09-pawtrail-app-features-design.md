# 조심해야댕(PawTrail) 앱 — 지도/게임화 기능 이식 설계

- 작성일: 2026-07-09
- 대상 앱: `docs/app/` (생성원본: `scripts/make_app.py`)
- 원본 기능: `~/Downloads/PawTrail 안전 산책 UI 3/조심해야댕.dc.html` (디자인캔버스 export)
- 상태: **승인됨** (사용자 "이대로 진행해줘")

## 1. 목표

`UI 3` 폴더의 완성된 7개 화면·게임화 기능을 **내 앱의 주황(#F1592A)/Gothic A1 디자인으로 리스킨해 이식**하고, 지도를 **네이버 지도(Dynamic Map)** 로 교체하되 **실제 Azure GPS 라우팅을 유지**한다.

원본(UI 3)은 React식 `support.js` 런타임 + 초록/크림 테마. 내 앱은 **바닐라 JS + Leaflet + 주황 테마**. → 로직을 바닐라 JS로 옮기고 리스킨한다.

## 2. 아키텍처 / 작업 위치

- **모든 수정은 `scripts/make_app.py`의 `HTML` 템플릿 문자열에서** 한다. 빌드하면 `docs/app/index.html` + `docs/app/조심해야댕.html`이 생성된다(끝에서 `__DATA__`/`__API_BASE__` 치환).
- 신규 플레이스홀더 `__NAVER_KEY__` 추가 → `make_app.py`가 `.env`의 `NAVER_MAP_KEY`를 빌드 시 주입(현재 `API_BASE`와 동일 패턴). `make_app.py`가 `.env`를 읽도록 로더 추가.
- 이미지 에셋: `UI 3/assets/`의 png → **웹용 압축**(리사이즈·최적화) 후 `docs/app/assets/`로 복사.
- 엔진/서버/`map_data.json`/위험지수/라우팅 로직은 **변경하지 않는다**. 코인 위치는 클라이언트에서 경로 지오메트리로 생성.

## 3. 화면 (7개)

| 화면 | 기존 | 작업 |
|------|------|------|
| 홈 | 있음 | 강아지 아바타(옷 반영)→댕꾸, 코인 잔액칩→상점, 지도 진입 추가 |
| 안전경로지도 | 부분(경로화면) | 네이버 지도 + 레이어칩 + 안전지점 마커 + 경로 상세카드 (신규 화면화) |
| POI목록 / POI상세 | 부분 | 급수대·놀이터 등 목록 + 🎁보상 표시 |
| 산책중 | 있음(정적) | 진행 애니메이션 + 경로 위 코인 줍기 |
| 댕꾸 | **신규** | 견종 도감 선택 + 옷 입히기/변경/벗기기 |
| 상점 | **신규** | 옷 6종 구매(코인 차감) |

## 4. 지도 — 네이버 Dynamic Map + 실제 경로

- `<head>`에 로더: `https://oapi.map.naver.com/openapi/v3/maps.js?ncpKeyId=__NAVER_KEY__`
- `getMap()`/`renderMap()`를 Leaflet → 네이버로 교체:
  - `naver.maps.Map`, `naver.maps.Polyline`(그늘색 세그먼트), `naver.maps.Marker`(POI/출·착/강아지, `icon.content`로 커스텀 HTML)
  - 입력은 기존 `DATA.routes[].segs[].line/shade`, `DATA.routes[].pois` 그대로 → **실제 라우팅 유지**
- `window.navermap_authFailure` 정의 → 인증 실패 시 안내 메시지 노출
- **사용자 액션(콘솔)**: Maps Application 생성 + Dynamic Map 선택 + Web 서비스 URL 등록(`https://heonjaeh-lab.github.io`, `http://localhost:8000`, 필요시 `file://`)

## 5. 코인 — 산책하며 줍기

- 선택 경로 폴리라인 위에 코인 N개 균등 배치.
- 산책 진행(강아지 마커 전진; GPS 가능 시 실측 위치)에서 근접 코인 +1씩 획득 + **완주 보너스**.
- 잔액은 `localStorage` 저장. 초기값 1000.

## 6. 댕꾸 (강아지 고르기 + 옷)

- 견종 도감: **말티즈 / 포메라니안 / 골든두들** 중 활성 강아지 선택.
- 옷: 보유 옷 **입히기 / 변경 / 벗기기**. 조합 이미지 `assets/dog-{breed}-{outfit}.png`(없으면 기본 `dog-{breed}.png`). 홈 아바타·산책 마커에 즉시 반영.
- 로직: `dressedImg(breed, outfit)`, `DRESSED` 조합 맵, `equip/remove`.

## 7. 상점

- 옷 6종: 턱시도(100) · 교복(200) · 군복/메시/웨딩/두산(각 300), 등급 라벨(스탠다드/레어/에픽).
- 구매 → 코인 차감·`owned` 추가. 이미 보유/코인 부족 시 토스트 메시지.
- 진입: 홈 코인칩 + 댕꾸 화면.

## 8. 상태 / 영속

- `localStorage` 키 하나에 `{coins, owned:[], breed, outfit}` 저장/복원.
- **가정**: 댕꾸에서 고른 견종을 마이/프로필의 활성 견종과 연동(아바타=활성견). 분리 원하면 조정.

## 9. 디자인 (리스킨)

- 내 앱이 이미 "디자인 개선본"(주황 #F1592A + Gothic A1)이므로, UI3(초록/크림)의 **구조만** 가져와 주황 테마로 리스킨. 기존 CSS 컴포넌트(`.card/.btn/.chip/.rchip/.toggle/.tab` 등) 재사용.
- "현재 디자인 유지 = 개선본 일치"가 자연히 충족.

## 10. 에셋

- 강아지 21장(기본3 + 착용조합18) + 아이템 6장 + `coin.png`.
- 원본 1.5~2.4MB/장 → 압축(리사이즈 ~800px, 최적화)해 저장소·Pages 부담 완화.

## 11. 범위 밖 / 리스크

- 범위 밖: 엔진/서버/데이터/위험지수/라우팅 알고리즘.
- 리스크: 네이버 도메인 미등록 시 인증 실패(사용자 콘솔 작업 필요), `file://` 직접 열기 제약(로컬 서버 권장), 에셋 용량.
