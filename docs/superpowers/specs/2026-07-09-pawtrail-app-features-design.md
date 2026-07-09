# 조심해야댕(PawTrail) 앱 — v5 디자인 리스타일 + 지도/게임화 기능 이식 설계

- 작성일: 2026-07-09 (v5 디자인 확정 반영해 개정)
- 대상 앱: `docs/app/` (생성원본: `scripts/make_app.py`)
- **기능 원본**: `~/Downloads/PawTrail 안전 산책 UI 3/조심해야댕.dc.html` (지도·안전지점·코인·댕꾸·상점)
- **디자인 원본(개선본 v5)**: `~/Downloads/Shared link 2/조심해야댕.dc.html`
- 상태: **승인됨** (지도=네이버+실제경로, 코인=산책하며 줍기)

## 1. 목표

내 앱을 **v5 디자인(코랄/크림·Pretendard+Jua·3D 이모지·걷는 강아지 영상)으로 전면 리스타일**하고, `UI 3`의 기능(**네이버 지도 + 실제 경로, 산책하며 코인 줍기, 댕꾸(강아지 고르기+옷 입히기), 상점**)을 v5 디자인 언어로 이식한다. 데이터·라우팅 로직(DATA/API_BASE/Azure)은 유지한다.

> v5 원본은 line 252에서 `https://heonjaeh-lab.github.io/project-uos/app/assets/mandu.png`를 참조 → **v5는 곧 내 앱(docs/app)의 목표 디자인**이다. 즉 v5의 마크업/스타일을 가져와 내 앱의 데이터 배선에 얹는다.

## 2. 아키텍처 / 작업 위치

- **모든 수정은 `scripts/make_app.py`의 `HTML` 템플릿 문자열**. 빌드 → `docs/app/index.html`(+`조심해야댕.html`) 생성(`__DATA__`/`__API_BASE__` 치환).
- 신규 플레이스홀더 `__NAVER_KEY__` 추가 → `.env`의 `NAVER_MAP_KEY`(=`86ibnd4q5w`, 검증됨) 주입. make_app.py가 `.env`를 읽도록 로더 추가.
- 엔진/서버/`map_data.json`/위험지수/라우팅 로직은 **변경 안 함**. 코인 위치는 경로 지오메트리로 클라이언트 생성.

## 3. 디자인 토큰 (v5, 리스타일 기준)

- 폰트: 본문 **Pretendard**(jsdelivr CDN) + 디스플레이 **Jua**(워드마크·대형 숫자/제목).
- 색: 폰프레임 `#FDF3F0`, 페이지 `#F3E4DD`/radial `#FBEFEA→#F0DDD5`; 텍스트 `#23201B`; 워드마크 빨강 `#FF3131`; 코랄 `#EC968C`/`#F2A492`(버튼·위험카드), 라이트 `#FCEDE8`/`#FCE7DF`; 정보카드 블루 `#EAF1F6`; 안전 그린 `#74C39B`/`#CFE3D0`; 골드 `#F1C36B`; 보더 `#E5DFD2`.
- 버튼: 코랄 bg, `#23201B` 텍스트, `border-radius:20px`, 큰 소프트 섀도우.
- 아이콘: **3D 이모지** `cdn.jsdelivr.net/gh/shuding/fluentui-emoji-unicode/assets/{code}_3d.png`(🐾1f43e·🌲1f332·📍1f4cd·🐕1f415·💩1f4a9·💧1f4a7·🎉1f389 등). 폰트 CDN처럼 외부 로드 허용.
- 애니메이션: `floatPaw`·`popIn`·`riseIn`·`pulseDot`·`sigPulse`.

## 4. 화면 (v5 리스타일 + 신규)

| 화면 | 내용 | 출처 |
|------|------|------|
| 홈 | 걷는 강아지 히어로 + 워드마크 + 코랄 위험카드(신호등) + 시간별 위험지수 | v5 |
| 안전한 길(경로/지도) | 네이버 지도 + 코랄 경로선 + POI마커 + 추천 경로카드(거리/시간/그늘/안전지점) | v5+UI3 |
| 산책중 | 진행 + "다음 안전지점까지 Nm" + 코인 줍기 | v5+UI3 |
| 완료 | 🎉 + 만두 + 격려 메시지 | v5 |
| 프로필/온보드 | 견종·단두종·지병 → 개인화 안내 | v5 |
| 기록 | 주간 함께한 시간 + **대변·소변 주간 막대그래프**(poopWeeks) | v5 |
| **댕꾸** | 강아지 고르기(도감) + 옷 입히기/변경/벗기기 | UI3(신규, v5 스타일) |
| **상점** | 옷 6종 구매(코인 차감) | UI3(신규, v5 스타일) |

## 5. 걷는 강아지 히어로 (v5 시그니처)

- 숨긴 `<video src="assets/walk.mp4" muted loop playsinline>` + `<canvas>`.
- 매 프레임(≈24fps) `drawImage`(영역 SX0/SY155/SW720/SH850→270×319) → `getImageData` → **테두리에서 플러드필로 어두운 배경(max(rgb)<60) 제거** → 가장자리 알파 페더 → `putImageData`. drop-shadow로 입체감.
- v5 HTML 672-721의 `videoRef`/`dogCanvasRef` 로직을 **바닐라로 그대로 이식**(프레임워크 비의존). `walk.mp4`를 `docs/app/assets/`로 복사.

## 6. 지도 — 네이버 Dynamic Map + 실제 경로

- `<head>` 로더 `...maps.js?ncpKeyId=__NAVER_KEY__`. `getMap()`/`renderMap()`를 Leaflet→네이버로 교체(`naver.maps.Map/Polyline/Marker`), 입력은 기존 `DATA.routes[].segs/pois` 유지 → 실제 라우팅 유지. 경로선 코랄. `window.navermap_authFailure` 안내.
- 콘솔(완료됨): Maps App `86ibnd4q5w`, Dynamic Map 선택, Web URL에 `https://heonjaeh-lab.github.io`·`http://localhost:8000` 등록.

## 7. 코인 — 산책하며 줍기

- 선택 경로 폴리라인 위 코인 균등 배치 → 진행하며 근접 코인 +1 + 완주 보너스. `localStorage` 저장(초기 1000).

## 8. 댕꾸 / 상점 (UI3 기능, v5 스타일)

- 댕꾸: 견종 도감(말티즈/포메/골든두들) 선택 + 보유 옷 입히기/변경/벗기기. 조합 이미지 `assets/dog-{breed}-{outfit}.png`(없으면 기본) → 홈 히어로·산책 마커 반영.
- 상점: 옷 6종(턱시도100·교복200·군복/메시/웨딩/두산 각300) 구매 → 코인 차감/보유/부족 메시지.
- 상태 `localStorage` `{coins, owned:[], breed, outfit}`. **가정**: 댕꾸 견종 = 프로필 활성견과 연동.

## 9. 에셋

- `walk.mp4`(≈0.5MB) + 강아지 21장(기본3+조합18) + 아이템 6장 + `coin.png` → **웹용 압축**(sips 리사이즈·최적화) 후 `docs/app/assets/` 복사. 3D 이모지는 CDN 사용.

## 10. 범위 밖 / 리스크

- 범위 밖: 엔진/서버/데이터/위험지수/라우팅 알고리즘.
- 리스크: 네이버 도메인/키(완료), 캔버스 키잉이 walk.mp4 배경(어두움) 가정에 의존, 에셋 용량, 3D 이모지·Pretendard CDN 오프라인 미표시.
