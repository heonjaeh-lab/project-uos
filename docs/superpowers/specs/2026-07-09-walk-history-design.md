# 산책 기록 — 걸었던 루트 보기 (MVP, A안)

- 날짜: 2026-07-09
- 상태: 승인됨(사용자) → 구현. **발표 내일** — 프론트+localStorage 전용, 엔진/Azure 변경 없음(배포=git push).
- 대상: `docs/app/index.html` 만.

## 배경
기록 탭(`#s-record`)은 현재 전부 하드코딩 목업(`WEEKLY`·`HISTORY`). 완주해도 아무것도 저장되지 않아 "내가 걸었던 루트"를 볼 수 없다.

## 범위 (A안)
완주 시 **사용자가 고른 추천 경로**를 기기(localStorage)에 저장하고, 기록 탭에서 목록·통계로 보여주며, 탭하면 그 경로를 지도에 다시 그린다. (실제 GPS 궤적=B안, 편집/삭제, 백엔드 동기화는 발표 후.)

## 데이터 (localStorage)
- 키 `pawtrail.walks` = 최신순 배열, 최대 50건.
- 레코드: `{ts, routeLabel, distance_m, time_min, shade, shade_eff, sky_code, coins, dogName, segs:[{line,shade,shade_eff}], demo}`.
- 헬퍼: `loadWalks()`(부팅), `saveWalks()`, `recordWalk()`(DATA.routes[sel]+meta 스냅샷 저장), `finishWalk()=recordWalk()+go('done')`.
- 완주 지점 배선: 자동완주(`_walkProg>=1`)·`endWalk()` 둘 다 `go('done')` → `finishWalk()`로 교체. 데모 완주도 저장(demo 플래그, 발표 시연용).

## UI
- **기록 탭 개편**(`renderRecord`): `WEEKLY`→실데이터. `#wkWalks`=총 횟수, `#wkKm`=총 거리(km), `#wkShade`=평균 실질그늘(%). `#wkChart`=최근 7일 일별 거리. `#histList`=저장 기록 카드(날짜·경로라벨·거리/시간/그늘, 탭→상세). 0건이면 빈 상태 문구.
- **상세 화면 신설**(`#s-recwalk`): 헤더(뒤로가기→record)+`.mapwrap #recMap`+통계행 `#recwStats`. `openWalk(i)`→`go('recwalk')`, `renderRecWalk()`가 `getMap`+`shadeColor(effVal(seg))`로 저장 segs를 그늘색 폴리라인으로 재그림(기존 지도 인프라 재사용) + 시작/끝 마커 + fitBounds. go() 스위치에 `recwalk` 추가.

## 실패안전/회귀
- localStorage 파싱 실패→빈 배열. `shade_eff` 없던 구 레코드→`shade` 폴백. 기존 `WEEKLY`/`HISTORY` 상수는 제거 안 하고 미사용화(POOP는 배변화면이 계속 사용). 지도 없으면(네이버 미인증/오프라인) 상세는 통계만.
- 엔진/서버/테스트 불변 → pytest 영향 없음. `const DATA=` 앵커 라인 불변(make_app 안전).

## 배포
git push (GitHub Pages)만. Azure 재배포 불필요. 라이브 검증: 완주→기록 목록 1건 증가→탭→지도에 경로 표시.
