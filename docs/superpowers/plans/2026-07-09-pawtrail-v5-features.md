# 조심해야댕 v5 리스타일 + 지도/게임화 기능 이식 — 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 내 앱(`docs/app`)을 v5 디자인(코랄/크림·Pretendard+Jua·3D이모지·걷는 강아지 영상)으로 전면 리스타일하고, `UI 3`의 기능(네이버 지도+실제 경로, 산책하며 코인 줍기, 댕꾸, 상점)을 이식한다.

**Architecture:** 모든 편집은 `scripts/make_app.py`의 `HTML` 원시문자열 템플릿에서. 빌드하면 `docs/app/index.html`+`조심해야댕.html` 생성. v5 HTML은 마크업/스타일 원본, UI3 HTML은 기능 로직 원본, make_app.py는 데이터/API 배선. 지도만 Leaflet→네이버로 교체하고 나머지 데이터 흐름(DATA/API_BASE)은 유지.

**Tech Stack:** Python(빌드) · 바닐라 JS · 네이버 지도 v3 JS(`ncpKeyId`) · Pretendard+Jua(CDN) · fluentui 3D 이모지(CDN) · sips(이미지 압축) · pytest.

## Global Constraints

- 편집 대상은 **오직 `scripts/make_app.py`**. `docs/app/index.html`은 생성물이므로 직접 수정 금지.
- 빌드: `cd "/Users/haheonjae/시립대 문제 해결 프로젝트" && .venv/bin/python scripts/make_app.py`
- 테스트: `.venv/bin/python -m pytest -q`
- 로컬 확인: `cd docs/app && python3 -m http.server 8000` → `http://localhost:8000` (네이버 도메인 등록됨)
- 엔진/서버/`data/demo/map_data.json`/위험지수/라우팅 **변경 금지**.
- **네이버 키**: `.env`의 `NAVER_MAP_KEY=86ibnd4q5w` (Client ID, 공개값). 로더 `https://oapi.map.naver.com/openapi/v3/maps.js?ncpKeyId=<KEY>`. 인증실패 시 `window.navermap_authFailure`.
- **v5 디자인 토큰** (verbatim):
  - 폰트: 본문 `Pretendard`, 디스플레이 `'Jua',cursive`
  - 폰프레임 `#FDF3F0` / 페이지 radial `#FBEFEA→#F0DDD5` / body `#F3E4DD`
  - 텍스트 `#23201B` · 워드마크 `#FF3131` · 코랄 `#EC968C`/`#F2A492`(버튼·위험카드) · 라이트코랄 `#FCEDE8`/`#FCE7DF` · 블루카드 `#EAF1F6` · 그린 `#74C39B`/`#CFE3D0` · 골드 `#F1C36B` · 보더 `#E5DFD2`
  - 버튼: `background:#EC968C;color:#23201B;border-radius:20px;padding:17px;box-shadow:0 12px 24px -10px rgba(30,122,84,.6)`
  - 3D 이모지: `https://cdn.jsdelivr.net/gh/shuding/fluentui-emoji-unicode/assets/{code}_3d.png` (🐾`1f43e` 🌲`1f332` 📍`1f4cd` 🐕`1f415` ☔`2614` 💩`1f4a9` 💧`1f4a7` 🎉`1f389` 🐭`1f43d`)
  - 키프레임: `floatPaw`,`popIn`,`riseIn`,`pulseDot`,`sigPulse`
- **소스 참조**: 디자인 `~/Downloads/Shared link 2/조심해야댕.dc.html` (v5), 기능 `~/Downloads/PawTrail 안전 산책 UI 3/조심해야댕.dc.html` (UI3).

---

### Task 1: 빌드 배선 — .env 로드 + 네이버 키 주입 + 헤드/셸 v5화

**Files:**
- Modify: `scripts/make_app.py` (상단 env 로직 + `HTML` 템플릿 `<head>`/`<body>` 셸 + 말미 `.replace`)
- Create: `tests/test_app_build.py`

**Interfaces:**
- Produces: 빌드 산출 HTML에 `ncpKeyId=86ibnd4q5w` 로더, Pretendard 링크, v5 body/frame CSS, `window.navermap_authFailure` 스텁. `__NAVER_KEY__` 잔여 없음.

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_app_build.py`

```python
import subprocess, sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]

def build():
    r = subprocess.run([sys.executable, "scripts/make_app.py"], cwd=ROOT,
                        capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return (ROOT / "docs/app/index.html").read_text(encoding="utf-8")

def test_naver_loader_injected():
    html = build()
    assert "oapi.map.naver.com/openapi/v3/maps.js?ncpKeyId=" in html
    assert "__NAVER_KEY__" not in html            # 플레이스홀더 잔여 없음
    assert "ncpKeyId=86ibnd4q5w" in html           # .env 값 주입

def test_v5_shell_present():
    html = build()
    assert "pretendard" in html.lower()            # 본문 폰트
    assert "navermap_authFailure" in html          # 인증 실패 훅
    assert "#FDF3F0" in html                        # v5 폰프레임 색
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `.venv/bin/python -m pytest tests/test_app_build.py -q`
Expected: FAIL (`ncpKeyId=` 없음 / `__NAVER_KEY__` 잔여)

- [ ] **Step 3: make_app.py 상단에 .env 로더 + 키 변수 추가**

`API_BASE = os.environ.get(...)` 근처(라인 12 부근)에 추가:

```python
def _load_env(path=".env"):
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), path)
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
_load_env()
NAVER_KEY = os.environ.get("NAVER_MAP_KEY", "")
```

- [ ] **Step 4: `<head>` 교체 — Leaflet 제거, 네이버+Pretendard 추가**

템플릿 `<head>`의 기존 폰트 `<link>`와 Leaflet `<link>/<script>`를 아래로 교체:

```html
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Jua&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css">
<script src="https://oapi.map.naver.com/openapi/v3/maps.js?ncpKeyId=__NAVER_KEY__"></script>
```

- [ ] **Step 5: body/frame v5 기본 CSS + 키프레임으로 교체**

템플릿 `<style>`의 body/phone/scr 규칙을 v5 토큰으로:

```css
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
body{margin:0;background:#F3E4DD;font-family:'Pretendard','Jua',system-ui,sans-serif}
::-webkit-scrollbar{width:0;height:0}
.wrap{display:flex;justify-content:center;padding:22px;min-height:100vh;background:radial-gradient(120% 90% at 50% 0%,#FBEFEA 0%,#F0DDD5 100%)}
.phone{width:390px;height:844px;background:#FDF3F0;border-radius:44px;overflow:hidden;position:relative;display:flex;flex-direction:column;box-shadow:0 30px 70px -20px rgba(60,50,30,.45),0 0 0 1px rgba(0,0,0,.03)}
.scr{position:absolute;inset:0;display:none;flex-direction:column;background:#FDF3F0}
.scr.on{display:flex}
@keyframes floatPaw{0%,100%{transform:translateY(0) rotate(-4deg)}50%{transform:translateY(-7px) rotate(4deg)}}
@keyframes popIn{0%{transform:scale(.7);opacity:0}60%{transform:scale(1.06)}100%{transform:scale(1);opacity:1}}
@keyframes riseIn{0%{transform:translateY(10px);opacity:0}100%{transform:translateY(0);opacity:1}}
@keyframes pulseDot{0%{box-shadow:0 0 0 0 rgba(47,163,107,.5)}70%{box-shadow:0 0 0 14px rgba(47,163,107,0)}100%{box-shadow:0 0 0 0 rgba(47,163,107,0)}}
@keyframes sigPulse{0%,100%{transform:scale(1);opacity:1}50%{transform:scale(1.14);opacity:.82}}
```

- [ ] **Step 6: authFailure 스텁 추가** (JS 영역 최상단)

```javascript
window.navermap_authFailure=function(){
  document.querySelectorAll('.mapwrap').forEach(function(el){
    el.innerHTML='<div style="display:flex;align-items:center;justify-content:center;height:100%;padding:16px;text-align:center;font-size:12.5px;color:#B85C50;background:#FCEDE8">지도 인증 실패<br>NCP 콘솔 Web 서비스 URL에 이 주소를 등록해 주세요</div>';
  });
};
```

- [ ] **Step 7: 말미 치환에 네이버 키 추가**

`out = HTML.replace("__DATA__", ...).replace("__API_BASE__", ...)` 체인에 추가:

```python
out = out.replace("__NAVER_KEY__", NAVER_KEY)
```

- [ ] **Step 8: 빌드 + 테스트 통과 확인**

Run: `.venv/bin/python scripts/make_app.py && .venv/bin/python -m pytest tests/test_app_build.py -q`
Expected: PASS (2 passed)

- [ ] **Step 9: 커밋**

```bash
git add scripts/make_app.py tests/test_app_build.py docs/app/index.html "docs/app/조심해야댕.html"
git commit -m "feat(app): v5 셸+네이버 로더 배선 (.env NAVER_MAP_KEY 주입, Pretendard, authFailure)"
```

---

### Task 2: 에셋 압축·복사 (walk.mp4 + 강아지 + 아이템 + 코인)

**Files:**
- Create: `scripts/copy_v5_assets.sh`
- Create(출력): `docs/app/assets/walk.mp4`, `dog-*.png`(21), `item-*.png`(6), `coin.png`

**Interfaces:**
- Produces: `docs/app/assets/`에 `walk.mp4`, `dog-{maltese,pom,goldendoodle}.png`, `dog-{breed}-{tuxedo,uniform,military,messi,wedding,doosan}.png`, `item-{...}.png`, `coin.png` (각 ≤400KB, walk.mp4 원본).

- [ ] **Step 1: 복사·압축 스크립트 작성** — `scripts/copy_v5_assets.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail
UI3="/Users/haheonjae/Downloads/PawTrail 안전 산책 UI 3/assets"
V5="/Users/haheonjae/Downloads/Shared link 2/assets"
OUT="$(cd "$(dirname "$0")/.." && pwd)/docs/app/assets"
mkdir -p "$OUT"
cp "$V5/walk.mp4" "$OUT/walk.mp4"                       # 영상 원본(0.5MB)
for f in "$UI3"/dog-*.png "$UI3"/item-*.png "$UI3"/coin.png; do
  base="$(basename "$f")"
  cp "$f" "$OUT/$base"
  sips --resampleWidth 720 "$OUT/$base" >/dev/null       # 폭 720으로 리샘플(고해상 3D → 웹용)
done
echo "copied to $OUT"; ls -la "$OUT" | tail -30
```

- [ ] **Step 2: 실행**

Run: `bash scripts/copy_v5_assets.sh`
Expected: `docs/app/assets`에 28+개 파일, dog/item png가 수백 KB로 축소.

- [ ] **Step 3: 용량 검증 테스트 추가** — `tests/test_app_build.py`에 추가

```python
def test_v5_assets_present_and_small():
    a = ROOT / "docs/app/assets"
    for name in ["walk.mp4", "coin.png", "dog-maltese.png",
                 "dog-goldendoodle-tuxedo.png", "item-wedding.png"]:
        f = a / name
        assert f.exists(), f"missing {name}"
    for png in a.glob("dog-*.png"):
        assert png.stat().st_size < 700_000, f"{png.name} too big"
```

Run: `.venv/bin/python -m pytest tests/test_app_build.py -q` → PASS

- [ ] **Step 4: 커밋**

```bash
git add scripts/copy_v5_assets.sh docs/app/assets tests/test_app_build.py
git commit -m "feat(app): v5 에셋 복사·압축 (walk.mp4 + 강아지21 + 아이템6 + coin)"
```

---

### Task 3: 걷는 강아지 히어로 (video→canvas 배경제거)

**Files:**
- Modify: `scripts/make_app.py` (홈 히어로 마크업 + JS `initDogHero`)

**Interfaces:**
- Consumes: `assets/walk.mp4` (Task 2)
- Produces: `initDogHero()` — 홈의 `#dogVideo`/`#dogCanvas`를 구동. `startDogHero()`/`stopDogHero()` 노출.

- [ ] **Step 1: 홈 히어로 마크업** (홈 화면 상단, v5 라인 44-47 대응)

```html
<div id="heroBox" onclick="go('profile')" style="width:160px;height:189px;cursor:pointer;position:relative;margin:0 auto 14px">
  <video id="dogVideo" src="assets/walk.mp4" muted playsinline loop style="position:absolute;left:0;top:0;width:2px;height:2px;opacity:0;pointer-events:none"></video>
  <canvas id="dogCanvas" style="width:100%;height:100%;display:block;filter:drop-shadow(0 9px 9px rgba(190,120,105,.3))"></canvas>
  <img id="heroStill" alt="" style="display:none;width:100%;height:100%;object-fit:contain;filter:drop-shadow(0 9px 9px rgba(190,120,105,.3))">
</div>
```

- [ ] **Step 2: 캔버스 배경제거 JS** (v5 672-721 이식, 바닐라)

```javascript
let _dogRAF=0;
function initDogHero(){
  const vid=$('dogVideo'), cvs=$('dogCanvas');
  if(!vid||!cvs)return;
  vid.play&&vid.play().catch(()=>{});
  vid.addEventListener('ended',()=>{vid.currentTime=0;vid.play().catch(()=>{});});
  const BW=270,BH=319,SX=0,SY=155,SW=720,SH=850;
  cvs.width=BW;cvs.height=BH;
  const ctx=cvs.getContext('2d',{willReadFrequently:true});
  const q=new Int32Array(BW*BH), bgm=new Uint8Array(BW*BH); let last=0;
  const tick=(t)=>{
    if(!cvs.isConnected){_dogRAF=0;return;}
    _dogRAF=requestAnimationFrame(tick);
    if(vid.readyState<2)return; if(t-last<42)return; last=t;
    ctx.clearRect(0,0,BW,BH); ctx.drawImage(vid,SX,SY,SW,SH,0,0,BW,BH);
    const img=ctx.getImageData(0,0,BW,BH), p=img.data, N=BW*BH;
    bgm.fill(0); let qs=0,qe=0;
    const isBg=(i)=>{const o=i<<2;return Math.max(p[o],p[o+1],p[o+2])<60;};
    const push=(i)=>{if(!bgm[i]&&isBg(i)){bgm[i]=1;q[qe++]=i;}};
    for(let x=0;x<BW;x++){push(x);push((BH-1)*BW+x);}
    for(let y=0;y<BH;y++){push(y*BW);push(y*BW+BW-1);}
    while(qs<qe){const i=q[qs++],x=i%BW,y=(i/BW)|0;
      if(x>0)push(i-1);if(x<BW-1)push(i+1);if(y>0)push(i-BW);if(y<BH-1)push(i+BW);}
    for(let i=0;i<N;i++)if(bgm[i])p[(i<<2)+3]=0;
    for(let i=0;i<N;i++){if(bgm[i])continue;const o=i<<2;if(p[o+3]===0)continue;
      const x=i%BW,y=(i/BW)|0;
      if((x>0&&bgm[i-1])||(x<BW-1&&bgm[i+1])||(y>0&&bgm[i-BW])||(y<BH-1&&bgm[i+BW])){
        const mx=Math.max(p[o],p[o+1],p[o+2]);if(mx<150)p[o+3]=Math.round(mx/150*200);}}
    ctx.putImageData(img,0,0);
  };
  if(!_dogRAF)_dogRAF=requestAnimationFrame(tick);
}
```

- [ ] **Step 3: 홈 진입 시 구동** — `renderHome()` 끝에 `initDogHero();` 호출 추가.

- [ ] **Step 4: 빌드 + 브라우저 확인**

Run: `.venv/bin/python scripts/make_app.py`, 그리고 `docs/app`에서 `python3 -m http.server 8000`
확인: `http://localhost:8000` 홈에 **흰 강아지가 배경 없이 걷는 애니메이션** + 소프트 섀도우. (브라우저 콘솔 에러 없음)

- [ ] **Step 5: 커밋**

```bash
git add scripts/make_app.py docs/app/index.html "docs/app/조심해야댕.html"
git commit -m "feat(app): 걷는 강아지 히어로 (walk.mp4 캔버스 배경제거 이식)"
```

---

### Task 4: 홈 화면 v5 리스타일

**Files:** Modify `scripts/make_app.py` (홈 `.scr` 마크업 + `renderHome()`)

**Interfaces:**
- Consumes: 기존 `DATA.meta`(now_level/now_score/temp 등), `DATA.hourly`, `advisoryView()`, `initDogHero()`(T3)
- Produces: v5 홈 DOM. 위험 신호(green/yellow/red)를 코랄 배너 + 신호등 도트로 표현.

- [ ] **Step 1: 홈 마크업 교체** (v5 39-72 대응, 실데이터 id 유지)

핵심 구조(요약 — v5 원본 스타일 값 사용):
```html
<div class="scr on" data-t="home" id="scr-home"><div class="body" style="padding:6px 20px 28px">
  <div style="margin-bottom:10px">
    <div style="font-size:13px;font-weight:500;color:#23201B;letter-spacing:.02em">안전 산책 도우미</div>
    <div style="font-size:26px;color:#FF3131;font-family:'Jua',cursive">조심해야댕 <img src="https://cdn.jsdelivr.net/gh/shuding/fluentui-emoji-unicode/assets/1f43e_3d.png" style="width:1em;height:1em;vertical-align:-.14em"></div>
  </div>
  <!-- 히어로(Task 3 heroBox 삽입) -->
  <div id="riskCard"></div>            <!-- renderHome이 채움: 코랄 배너 -->
  <div style="margin-top:22px;display:flex;justify-content:space-between;margin-bottom:12px">
    <div style="font-size:17px;font-weight:600;color:#23201B">시간별 위험지수</div>
    <div style="font-size:12.5px;color:#23201B">매시간 갱신</div>
  </div>
  <div style="background:#fff;border-radius:24px;padding:18px 6px 14px;box-shadow:0 6px 18px -10px rgba(60,50,30,.25)">
    <div id="hrow" style="display:flex;overflow-x:auto;gap:4px;padding:0 12px 4px"></div>
  </div>
  <button onclick="findRoute()" style="margin-top:20px;width:100%;border:none;background:#EC968C;color:#23201B;font-family:inherit;font-size:16px;font-weight:600;padding:17px;border-radius:20px;box-shadow:0 12px 24px -10px rgba(30,122,84,.6)">🐾 안전한 길 찾기</button>
</div></div>
```

- [ ] **Step 2: `renderHome()` — 코랄 위험카드 생성**

신호 레벨별 코랄/옐로/레드 배경 + 신호등 도트. `SIG`(기존 green/yellow/red) 재사용, 카드 배경만 v5 코랄톤:
```javascript
function renderHome(){
  const m=DATA.meta, adv=advisoryView();
  const lv=rainDemo?'red':m.now_level;
  const CARD={green:'linear-gradient(135deg,#EFA79B,#EC968C)',yellow:'linear-gradient(135deg,#F1C36B,#E8A94D)',red:'linear-gradient(135deg,#F2857A,#EA5B4E)'};
  const TITLE={green:'좋아요',yellow:'주의해요',red:'위험해요'};
  const BADGE={green:'위험지수 낮음',yellow:'위험지수 보통',red:'위험지수 높음'};
  const sub=`기온 ${m.temp||'—'} · 그늘 ${m.shade_word||'많음'} · 아스팔트 ${m.road_word||'시원'}`;
  $('riskCard').innerHTML=`<div style="position:relative;border-radius:24px;padding:20px 22px;color:#fff;background:${CARD[lv]};box-shadow:0 14px 30px -14px rgba(200,110,90,.7)">
    <div style="position:absolute;right:16px;top:16px;display:flex;flex-direction:column;gap:5px;background:rgba(255,255,255,.34);backdrop-filter:blur(4px);padding:7px 6px;border-radius:16px">
      ${['red','yellow','green'].map(c=>`<div style="width:11px;height:11px;border-radius:50%;background:${SIG[c]};${c===lv?'animation:sigPulse 1.4s infinite':'opacity:.35'}"></div>`).join('')}
    </div>
    <div style="font-size:14px;font-weight:500;opacity:.92">지금 만두랑 나가기</div>
    <div style="display:flex;align-items:baseline;gap:10px;margin-top:4px">
      <div style="font-size:40px;font-family:'Jua',cursive">${TITLE[lv]}</div>
      <span style="background:rgba(255,255,255,.22);padding:5px 12px;border-radius:100px;font-size:13px;font-weight:600;backdrop-filter:blur(4px)">${BADGE[lv]}</span>
    </div>
    <div style="font-size:13.5px;opacity:.9;margin-top:8px;line-height:1.5">${sub} 🐾<br>말티즈 만두 기준으로 계산했어요</div></div>`;
  // 시간별 스트립 (기존 로직 유지, 색만 v5)
  $('hrow').innerHTML=DATA.hourly.map(h=>{const col=h.rain?'#8FB8D0':SIG[h.level];
    return `<div style="flex:none;text-align:center;padding:6px 8px"><div style="font-size:11px;color:#23201B">${h.hour}</div><div style="width:26px;height:26px;border-radius:50%;background:${col};margin:6px auto 0"></div></div>`;}).join('');
  initDogHero();
}
```
(주: `m.temp/shade_word/road_word`가 DATA에 없으면 `advisoryView()`/기존 필드에서 채우거나 폴백 문자열 사용 — 기존 renderHome이 쓰던 필드를 그대로 재사용할 것.)

- [ ] **Step 3: 빌드 + 브라우저 확인** — 홈이 `final-home.png`와 일치(워드마크·걷는 강아지·코랄 카드·시간 스트립).

- [ ] **Step 4: 커밋**
```bash
git add scripts/make_app.py docs/app/index.html "docs/app/조심해야댕.html"
git commit -m "feat(app): 홈 v5 리스타일 (워드마크·코랄 위험카드·신호등 도트·시간별 스트립)"
```

---

### Task 5: 네이버 지도 렌더 교체 (Leaflet → 네이버)

**Files:** Modify `scripts/make_app.py` (`getMap`/`renderMap`/`divIcon`/`shadeColor` + `.mapwrap` CSS)

**Interfaces:**
- Consumes: `DATA.routes[idx].segs[].line/shade`, `.pois`, `DATA.gps`, `dressedImg()`(T7 전엔 `assets/dog-maltese.png` 폴백)
- Produces: `renderMap(elId, routeIdx, opts)` — 네이버 지도에 코랄 경로/마커. `MAPS` 캐시. `clearOverlays(M)`.

- [ ] **Step 1: `getMap`/`renderMap` 네이버로 재작성**

```javascript
const MAPS={};
function naverReady(){return typeof naver!=='undefined'&&naver.maps;}
function shadeColor(s){const a=[236,150,140],b=[116,195,155];s=Math.max(0,Math.min(1,s));
  return `rgb(${a.map((v,i)=>Math.round(v+(b[i]-v)*s)).join(',')})`;}   // 햇볕(코랄)→그늘(그린)
function getMap(elId,interactive){
  if(MAPS[elId])return MAPS[elId];
  if(!naverReady())return null;
  const map=new naver.maps.Map(elId,{zoomControl:false,logoControl:false,mapDataControl:false,scaleControl:false,
    draggable:!!interactive,pinchZoom:!!interactive,scrollWheel:!!interactive,disableDoubleClickZoom:!interactive,
    center:new naver.maps.LatLng(DATA.gps.lat,DATA.gps.lon),zoom:15});
  const M={map,overlays:[]}; MAPS[elId]=M; return M;
}
function clearOverlays(M){for(const o of M.overlays)o.setMap(null);M.overlays=[];}
function htmlMarker(M,lat,lon,html,ax,ay,z){
  M.overlays.push(new naver.maps.Marker({position:new naver.maps.LatLng(lat,lon),map:M.map,
    icon:{content:html,anchor:new naver.maps.Point(ax,ay)},zIndex:z||50}));
}
function renderMap(elId,routeIdx,opts){
  opts=opts||{}; const M=getMap(elId,!!opts.interactive); if(!M)return;
  clearOverlays(M);
  const rt=DATA.routes[routeIdx], toLL=c=>new naver.maps.LatLng(c[1],c[0]);
  const b=new naver.maps.LatLngBounds(toLL(rt.segs[0].line[0]),toLL(rt.segs[0].line[0]));
  for(const sg of rt.segs){const path=sg.line.map(toLL);path.forEach(ll=>b.extend(ll));
    M.overlays.push(new naver.maps.Polyline({map:M.map,path,strokeColor:'#fff',strokeWeight:9,strokeOpacity:.95}));
    M.overlays.push(new naver.maps.Polyline({map:M.map,path,strokeColor:shadeColor(sg.shade),strokeWeight:5,strokeOpacity:1}));}
  if(opts.detail!==false&&rt.pois)for(const p of rt.pois)
    htmlMarker(M,p.lat,p.lon,`<div class="mk-poi" style="--c:${poiColor(p.type)}"></div>`,8,8,40);
  const f=rt.segs[0].line[0],l=rt.segs[rt.segs.length-1].line.slice(-1)[0];
  htmlMarker(M,f[1],f[0],'<div class="mk-pin start"></div>',9,9,500);
  htmlMarker(M,l[1],l[0],'<div class="mk-pin end"></div>',9,9,500);
  if(opts.pos){const mid=rt.segs[Math.floor(rt.segs.length*0.42)].line[0];
    htmlMarker(M,mid[1],mid[0],`<div class="mk-dog"><img src="${(typeof dressedImg==='function')?dressedImg():'assets/dog-maltese.png'}"></div>`,21,21,1000);}
  M.map.fitBounds(b);
}
```

- [ ] **Step 2: 마커 CSS v5화** (`.mk-pin/.mk-poi/.mk-dog`)

```css
.mapwrap{border-radius:20px;overflow:hidden;background:#E7EEE1}
.mk-pin{width:18px;height:18px;border-radius:50%;border:3px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,.3)}
.mk-pin.start{background:#fff;border-color:#EC968C}
.mk-pin.end{background:#EC968C}
.mk-poi{width:16px;height:16px;border-radius:50%;background:#fff;border:3px solid var(--c);box-shadow:0 2px 6px rgba(0,0,0,.25)}
.mk-dog{width:42px;height:42px;border-radius:50%;overflow:hidden;border:3px solid #fff;background:#fff;box-shadow:0 4px 10px rgba(0,0,0,.3)}
.mk-dog img{width:100%;height:100%;object-fit:cover}
```

- [ ] **Step 3: 빌드 + 확인** — 경로 화면(`http://localhost:8000`)에서 **네이버 지도에 코랄 경로선 + 출/착/POI 마커** 표시. 콘솔에 authFailure 없음.

- [ ] **Step 4: 빌드 테스트에 네이버 사용 확인 추가**
```python
def test_uses_naver_not_leaflet():
    html = build()
    assert "naver.maps.Map" in html
    assert "L.tileLayer" not in html and "unpkg.com/leaflet" not in html
```
Run pytest → PASS

- [ ] **Step 5: 커밋**
```bash
git add scripts/make_app.py tests/test_app_build.py docs/app/index.html "docs/app/조심해야댕.html"
git commit -m "feat(app): 지도 Leaflet→네이버 교체 (실제 경로·코랄 폴리라인·v5 마커)"
```

---

### Task 6: 경로/안전한 길 화면 v5 리스타일 + 안전지점

**Files:** Modify `scripts/make_app.py` (route `.scr` 마크업 + `renderRoute()`/`selectRoute()`)

**Interfaces:**
- Consumes: `DATA.routes`, `renderMap()`(T5), `haversine()`
- Produces: v5 경로 화면 DOM (헤더·지도·GPS핀·추천 카드·안전지점 목록·산책시작 버튼).

- [ ] **Step 1: 마크업 교체** (v5 라인 130-192 대응). 헤더 "안전한 길" + `만두·말티즈·소형견`, `<div class="mapwrap" id="routeMap" style="height:210px">`, "📍 내 위치(GPS)에서" pill, `#rchips`(추천 카드), `#poiList`(안전지점), 하단 "이 길로 산책 시작" 버튼(→`go('walk')`). 색/폰트는 Global 토큰.

- [ ] **Step 2: `renderRoute()` — v5 카드/칩** (기존 데이터 유지, 스타일만 v5)

```javascript
function renderRoute(){
  $('rchips').innerHTML=DATA.routes.map((r,i)=>`<div onclick="selectRoute(${i})" style="background:#fff;border-radius:20px;padding:16px;margin-top:10px;box-shadow:0 6px 16px -10px rgba(60,50,30,.3);border:2px solid ${i===sel?'#EC968C':'transparent'}">
    <div style="display:flex;align-items:center;gap:10px"><img src="https://cdn.jsdelivr.net/gh/shuding/fluentui-emoji-unicode/assets/1f332_3d.png" style="width:26px;height:26px"><div style="flex:1"><div style="font-family:'Jua',cursive;font-size:17px;color:#23201B">${r.label}</div><div style="font-size:12px;color:#8A8378">${i===0?'그늘 최대 · 추천':'대체 경로'}</div></div>${i===sel?'<span style="color:#EC968C;font-size:18px">✓</span>':''}</div>
    <div style="display:flex;gap:8px;margin-top:12px">${[[`${(r.distance_m/1000).toFixed(1)}km`,'거리'],[`${Math.round(r.est_time_min)}분`,'예상 시간'],[`${Math.round(r.shade*100)}%`,'평균 그늘'],[`${(r.pois||[]).length}곳`,'안전지점']].map(([v,k])=>`<div style="flex:1;background:#FCEDE8;border-radius:14px;padding:10px 4px;text-align:center"><div style="font-family:'Jua',cursive;font-size:15px;color:#23201B">${v}</div><div style="font-size:10.5px;color:#8A8378;margin-top:2px">${k}</div></div>`).join('')}</div></div>`).join('');
  const r=DATA.routes[sel], g=DATA.gps;
  $('poiList').innerHTML=(r.pois&&r.pois.length)?r.pois.map(p=>{const d=Math.round(haversine(g.lat,g.lon,p.lat,p.lon)/10)*10;
    return `<div style="display:flex;align-items:center;gap:12px;background:#fff;border-radius:16px;padding:12px;margin-top:8px"><span style="width:40px;height:40px;border-radius:12px;background:${poiIconBg(p.type)};display:flex;align-items:center;justify-content:center">${POI_EMOJI(p.type)}</span><div style="flex:1"><div style="font-weight:600;color:#23201B">${POI_KO[p.type]||p.type}</div><div style="font-size:12px;color:#8A8378">${d}m · ${POI_SUB[p.type]||''}</div></div></div>`;}).join(''):'<div style="color:#8A8378;font-size:12.5px;padding:8px">이 경로 주변 등록된 안전지점이 없어요.</div>';
  renderMap('routeMap',sel,{detail:true,interactive:true});
}
function selectRoute(i){sel=i;renderRoute();}
```
`POI_EMOJI` 헬퍼 추가(3D 이모지 img 반환): 급수대=💧`1f4a7`, 병원=🏥`1f3e5`, 공원=🌳`1f333`, 화장실=🚻, 펫샵=🦴`1f9b4`.

- [ ] **Step 3: 빌드 + 확인** — 경로 화면이 `v5-routes.png`와 일치(코랄 경로·추천 카드 stat칩·안전지점 목록).

- [ ] **Step 4: 커밋**
```bash
git add scripts/make_app.py docs/app/index.html "docs/app/조심해야댕.html"
git commit -m "feat(app): 경로 화면 v5 리스타일 (추천 카드·stat칩·안전지점 목록)"
```

---

### Task 7: 게임화 코어 (상태·영속·상수·dressedImg·아바타)

**Files:** Modify `scripts/make_app.py` (JS 상수/상태/헬퍼)

**Interfaces:**
- Produces: 전역 `GAME`, `BREEDS/SHOP/DRESSED/COIN_TS/WALK_DUR`, `saveGame()`,`loadGame()`,`dressedImg(breed?,outfit?)`,`heroSrc()`,`addCoins(n)`,`renderCoinChips()`,`refreshAvatar()`.
- Consumes: 에셋(Task 2).

- [ ] **Step 1: 상수 + 상태 + 영속** (UI3 라인 783-834 이식)

```javascript
const BREEDS=[
  {id:'maltese',name:'말티즈',img:'assets/dog-maltese.png',size:'소형견',trait:'하얗고 사랑스러운 단짝. 더위에 조금 약해요.',tag:'☀️ 더위 주의'},
  {id:'pom',name:'포메라니안',img:'assets/dog-pom.png',size:'소형견',trait:'폭신폭신 솜뭉치. 두꺼운 털로 여름엔 각별히 조심.',tag:'🌡️ 열 조심'},
  {id:'goldendoodle',name:'골든두들',img:'assets/dog-goldendoodle.png',size:'소형견',trait:'곱슬곱슬 다정한 아이. 산책과 물놀이를 좋아해요.',tag:'💧 활동 좋아'}];
const SHOP=[
  {id:'tuxedo',name:'턱시도',img:'assets/item-tuxedo.png',price:100,rank:'💫 스탠다드'},
  {id:'uniform',name:'교복',img:'assets/item-uniform.png',price:200,rank:'✨ 레어'},
  {id:'military',name:'군복',img:'assets/item-military.png',price:300,rank:'👑 에픽'},
  {id:'messi',name:'메시 유니폼',img:'assets/item-messi.png',price:300,rank:'👑 에픽'},
  {id:'wedding',name:'웨딩드레스',img:'assets/item-wedding.png',price:300,rank:'👑 에픽'},
  {id:'doosan',name:'두산 베어스 유니폼',img:'assets/item-doosan.png',price:300,rank:'👑 에픽'}];
const DRESSED={tuxedo:true,uniform:true,military:true,messi:{maltese:1,pom:1,goldendoodle:1},wedding:{maltese:1,pom:1,goldendoodle:1},doosan:{maltese:1,pom:1,goldendoodle:1}};
const COIN_TS=[0.125,0.375,0.625,0.875], WALK_DUR=22;
let GAME={coins:1000,owned:{},breed:'maltese',outfit:null};
function loadGame(){try{const s=JSON.parse(localStorage.getItem('pawtrail_game')||'null');if(s)GAME=Object.assign(GAME,s);}catch(e){}}
function saveGame(){try{localStorage.setItem('pawtrail_game',JSON.stringify(GAME));}catch(e){}}
function hasDressed(b,o){const d=DRESSED[o];if(!d)return false;return d===true?true:!!d[b];}
function dressedImg(b,o){b=b||GAME.breed;o=(o===undefined)?GAME.outfit:o;
  const base=(BREEDS.find(x=>x.id===b)||BREEDS[0]).img;
  return (o&&hasDressed(b,o))?`assets/dog-${b}-${o}.png`:base;}
function heroSrc(){return dressedImg();}
function addCoins(n){GAME.coins=Math.max(0,GAME.coins+n);saveGame();renderCoinChips();}
function renderCoinChips(){document.querySelectorAll('.coinval').forEach(el=>el.textContent=GAME.coins);}
```

- [ ] **Step 2: 아바타 반영 — heroBox가 옷/견종 반영**

`initDogHero()` 시작부에 분기 추가: 기본(maltese·무착용)이면 걷는 영상, 아니면 `#heroStill`에 `heroSrc()` 정적 이미지 표시.
```javascript
function refreshAvatar(){
  const vid=$('dogVideo'),cvs=$('dogCanvas'),still=$('heroStill');
  const animated=(GAME.breed==='maltese'&&!GAME.outfit);
  if(!vid)return;
  if(animated){still.style.display='none';cvs.style.display='block';vid.style.display='';initDogHero();}
  else{cvs.style.display='none';vid.style.display='none';still.style.display='block';still.src=heroSrc();}
}
```
`renderHome()`의 `initDogHero()` 호출을 `refreshAvatar()`로 교체.

- [ ] **Step 3: 부팅 시 로드** — 앱 초기화(`go('home')` 최초 호출 전)에서 `loadGame();renderCoinChips();`.

- [ ] **Step 4: 빌드 + 확인** — 콘솔에서 `localStorage.setItem('pawtrail_game', JSON.stringify({coins:50,owned:{tuxedo:1},breed:'goldendoodle',outfit:'tuxedo'}))` 후 새로고침 → 히어로가 골든두들+턱시도 정적 이미지로, 코인 50 표시.

- [ ] **Step 5: 커밋**
```bash
git add scripts/make_app.py docs/app/index.html "docs/app/조심해야댕.html"
git commit -m "feat(app): 게임화 코어 (BREEDS/SHOP/DRESSED·GAME 상태·localStorage·dressedImg·아바타)"
```

---

### Task 8: 댕꾸 화면 (강아지 고르기 + 옷 입히기)

**Files:** Modify `scripts/make_app.py` (`#scr-dress` `.scr` + `renderDress()` + 핸들러)

**Interfaces:**
- Consumes: `BREEDS/SHOP/DRESSED`,`GAME`,`dressedImg`,`saveGame`,`refreshAvatar`,`go`
- Produces: `openDress()`,`pickBreed(id)`,`openOutfitSheet()`,`equipOutfit(id)`,`removeOutfit()`,`renderDress()`.

- [ ] **Step 1: 마크업** — `<div class="scr" id="scr-dress">`: 헤더 "댕꾸 · 우리 아이 고르기", 견종 도감 카드 그리드(`#breedGrid`), 미리보기(`#dressPreview` = 큰 dressedImg), 착용 상태/버튼(입히기·변경·벗기기 = `#dressBtns`), 상점 가기 버튼(→`go('shop')`). v5 토큰(코랄/크림·Jua 제목).

- [ ] **Step 2: 핸들러 + `renderDress()`** (UI3 857-864,959-999 이식·바닐라)

```javascript
function openDress(){go('dress');}
function pickBreed(id){GAME.breed=id;saveGame();renderDress();refreshAvatar();}
function equipOutfit(id){GAME.outfit=id;saveGame();renderDress();refreshAvatar();}
function removeOutfit(){GAME.outfit=null;saveGame();renderDress();refreshAvatar();}
function renderDress(){
  $('breedGrid').innerHTML=BREEDS.map(b=>`<button onclick="pickBreed('${b.id}')" style="text-align:left;background:#fff;border:3px solid ${GAME.breed===b.id?'#EC968C':'#F2EDE2'};border-radius:20px;padding:12px;box-shadow:0 6px 14px -10px rgba(60,50,30,.3)">
    <img src="${b.img}" style="width:100%;height:88px;object-fit:contain"><div style="font-family:'Jua',cursive;font-size:15px;color:#23201B;margin-top:6px">${b.name}</div><div style="font-size:11px;color:#8A8378">${b.tag}</div></button>`).join('');
  $('dressPreview').src=dressedImg();
  const owned=SHOP.filter(s=>GAME.owned[s.id]);
  const cur=SHOP.find(s=>s.id===GAME.outfit);
  $('dressStatus').textContent=cur?`👔 ${cur.name} 착용 중`:'아직 맨몸이에요';
  $('dressBtns').innerHTML=owned.length?owned.map(o=>`<button onclick="equipOutfit('${o.id}')" style="background:${GAME.outfit===o.id?'#EC968C':'#FCEDE8'};color:#23201B;border:none;border-radius:14px;padding:10px 14px;font-family:inherit;font-weight:600">${o.name}${GAME.outfit===o.id?' ✓':''}</button>`).join('')+`<button onclick="removeOutfit()" style="background:#EAF1F6;color:#23201B;border:none;border-radius:14px;padding:10px 14px;font-weight:600">옷 벗기기</button>`
    :`<div style="font-size:12.5px;color:#8A8378">아직 보유한 옷이 없어요. <b style="color:#EC968C" onclick="go('shop')">상점</b>에서 구매하면 여기서 입혀볼 수 있어요.</div>`;
}
```

- [ ] **Step 3: 빌드 + 확인** — 댕꾸에서 견종 전환·(보유 옷) 착용/벗기기 → 미리보기 및 홈 히어로 반영. 미보유 시 안내.

- [ ] **Step 4: 커밋**
```bash
git add scripts/make_app.py docs/app/index.html "docs/app/조심해야댕.html"
git commit -m "feat(app): 댕꾸 화면 (강아지 도감 선택 + 옷 입히기/변경/벗기기)"
```

---

### Task 9: 상점 화면 (옷 구매)

**Files:** Modify `scripts/make_app.py` (`#scr-shop` `.scr` + `renderShop()` + `buyItem()`)

**Interfaces:**
- Consumes: `SHOP`,`GAME`,`addCoins`,`saveGame`,`renderDress`
- Produces: `openShop()`,`buyItem(id)`,`renderShop()`,`flashBuy(msg,kind)`.

- [ ] **Step 1: 마크업** — `<div class="scr" id="scr-shop">`: 헤더 "상점" + 코인 잔액(`.coinval`), 토스트(`#buyMsg`), 옷 목록(`#shopList`: 썸네일·이름·등급·가격·구매버튼). v5 토큰.

- [ ] **Step 2: 로직** (UI3 866-872 이식)

```javascript
let _buyT=0;
function openShop(){go('shop');}
function flashBuy(msg,kind){clearTimeout(_buyT);const el=$('buyMsg');
  el.textContent=msg;el.style.display='block';
  el.style.background=kind==='ok'?'#E7EEE1':kind==='no'?'#FCE7DF':'#EAF1F6';
  _buyT=setTimeout(()=>{el.style.display='none';},3200);}
function buyItem(id){const it=SHOP.find(s=>s.id===id);if(!it)return;
  if(GAME.owned[id]){flashBuy(it.name+'은(는) 이미 가지고 있어요','have');return;}
  if(GAME.coins<it.price){flashBuy('코인이 '+(it.price-GAME.coins)+'개 모자라요','no');return;}
  GAME.coins-=it.price;GAME.owned[id]=1;saveGame();renderCoinChips();renderShop();
  flashBuy('🎉 '+it.name+' 구매 완료! 댕꾸에서 입혀볼 수 있어요','ok');}
function renderShop(){
  $('shopList').innerHTML=SHOP.map(s=>{const owned=GAME.owned[s.id];
    return `<div style="display:flex;align-items:center;gap:12px;background:#fff;border-radius:18px;padding:12px;margin-top:10px;box-shadow:0 6px 14px -10px rgba(60,50,30,.3)">
      <img src="${s.img}" style="width:56px;height:56px;object-fit:contain;border-radius:12px;background:#FCEDE8">
      <div style="flex:1"><div style="font-family:'Jua',cursive;font-size:16px;color:#23201B">${s.name}</div><div style="font-size:11.5px;color:#8A8378">${s.rank}</div></div>
      <button onclick="buyItem('${s.id}')" ${owned?'disabled':''} style="border:none;border-radius:14px;padding:11px 16px;font-family:inherit;font-weight:700;background:${owned?'#E5DFD2':'#EC968C'};color:#23201B">${owned?'보유중':'🪙 '+s.price}</button>
    </div>`;}).join('');
}
```

- [ ] **Step 3: 빌드 + 확인** — 구매 시 코인 차감·보유표시·토스트, 코인 부족/이미 보유 경로 확인. 새로고침 후 보유 유지.

- [ ] **Step 4: 커밋**
```bash
git add scripts/make_app.py docs/app/index.html "docs/app/조심해야댕.html"
git commit -m "feat(app): 상점 화면 (옷 6종 구매·코인 차감·토스트·영속)"
```

---

### Task 10: 산책하며 코인 줍기

**Files:** Modify `scripts/make_app.py` (`renderWalk()`/`startWalk()`/`finishWalk()` + 코인 오버레이)

**Interfaces:**
- Consumes: `renderMap`,`COIN_TS`,`WALK_DUR`,`addCoins`,`DATA.routes`, 경로 지오메트리 헬퍼
- Produces: `pointAtFrac(rt,f)`, 산책 진행+코인 수집 루프.

- [ ] **Step 1: 경로 분위치 헬퍼**

```javascript
function routePts(rt){const a=[];for(const sg of rt.segs)for(const c of sg.line)a.push(c);return a;}
function pointAtFrac(rt,f){const pts=routePts(rt),cl=[0];
  for(let i=1;i<pts.length;i++)cl.push(cl[i-1]+haversine(pts[i-1][1],pts[i-1][0],pts[i][1],pts[i][0]));
  const total=cl[cl.length-1]||1,tg=total*f;
  for(let i=1;i<cl.length;i++)if(cl[i]>=tg){const t=(tg-cl[i-1])/((cl[i]-cl[i-1])||1);
    return [pts[i-1][0]+(pts[i][0]-pts[i-1][0])*t,pts[i-1][1]+(pts[i][1]-pts[i-1][1])*t];}
  return pts[pts.length-1];}
```

- [ ] **Step 2: 산책 진행 + 코인 수집** (UI3 875-892 이식, 실제 경로 좌표)

```javascript
let _walkT=0,_walkProg=0,_coinGot={};
function startWalk(){
  go('walk'); _walkProg=0;_coinGot={};
  const rt=DATA.routes[sel];
  renderMap('walkMap',sel,{detail:true,pos:true,interactive:false});
  const M=MAPS['walkMap'];
  // 코인 마커 배치
  const coinMk=COIN_TS.map((f,i)=>{const c=pointAtFrac(rt,f);
    const mk=new naver.maps.Marker({position:new naver.maps.LatLng(c[1],c[0]),map:M.map,
      icon:{content:'<div class="mk-coin"><img src="assets/coin.png"></div>',anchor:new naver.maps.Point(14,14)},zIndex:900});
    M.overlays.push(mk);return mk;});
  clearInterval(_walkT);
  _walkT=setInterval(()=>{
    _walkProg=Math.min(1,_walkProg+0.1/WALK_DUR);
    COIN_TS.forEach((f,i)=>{if(!_coinGot[i]&&_walkProg>=f){_coinGot[i]=1;coinMk[i].setMap(null);addCoins(1);
      const b=$('coinBurst');if(b){b.style.display='block';setTimeout(()=>b.style.display='none',700);}}});
    $('walkProgBar').style.width=Math.round(_walkProg*100)+'%';
    if(_walkProg>=1)finishWalk();
  },100);
}
function finishWalk(){clearInterval(_walkT);addCoins(1);go('done');}
```
(주: GPS 실시간 위치 사용 옵션은 `navigator.geolocation.watchPosition`으로 `_walkProg`를 실측 매핑하도록 후속 확장 가능. 기본은 데모 안정성 위해 애니메이션 진행.)

- [ ] **Step 3: 코인 마커 CSS + walk 화면 진행바/코인 잔액** (`.mk-coin`, `#walkProgBar`, `.coinval`, `#coinBurst`) 추가.

- [ ] **Step 4: 빌드 + 확인** — 산책 시작 → 강아지 마커 전진하며 코인 4개가 순차 사라지고 잔액 +1씩, 완주 시 +1 보너스 후 완료 화면.

- [ ] **Step 5: 커밋**
```bash
git add scripts/make_app.py docs/app/index.html "docs/app/조심해야댕.html"
git commit -m "feat(app): 산책하며 코인 줍기 (경로 위 코인 배치·수집·완주 보너스)"
```

---

### Task 11: 나머지 화면 v5(산책중/완료/프로필/기록+대변소변) + 네비 + 최종 검증

**Files:** Modify `scripts/make_app.py` (walk/done/profile/record `.scr` + 하단 네비 + `go()` 확장)

**Interfaces:**
- Consumes: 위 태스크 전부
- Produces: 완성된 화면 전환(`go('home'|'route'|'walk'|'done'|'profile'|'record'|'dress'|'shop')`), 하단 탭, 진입 동선.

- [ ] **Step 1: 산책중/완료 v5 마크업** — v5 200-256 대응. 산책중: `#walkMap`+진행바+"다음 안전지점까지 Nm →"+격려 말풍선+코인버스트. 완료: 🎉+`assets/mandu.png`+"오늘도 안전하게 다녀왔어" + 획득 코인 요약 + 홈으로.

- [ ] **Step 2: 프로필/온보드 v5** — v5 260-300 대응. 견종/단두종/지병 입력(기존 필드 id 유지) + "이 아이 기준 개인화" 안내 카드(`#EAF1F6`). 저장 시 `GAME.breed` 동기화(도감 3종과 매칭되면).

- [ ] **Step 3: 기록 화면 + 대변·소변 그래프** — v5 340-400 대응. 주간 함께한 시간 + `poopWeeks` 막대그래프:
```javascript
const POOP=[{label:'3주 전',poop:4,pee:11},{label:'2주 전',poop:7,pee:15},{label:'1주 전',poop:5,pee:12},{label:'이번 주',poop:6,pee:14}];
function renderRecord(){const max=16;
  $('poopChart').innerHTML=POOP.map(w=>`<div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:4px;justify-content:flex-end">
    <div style="display:flex;gap:3px;align-items:flex-end;height:120px">
      <div style="width:14px;border-radius:6px 6px 0 0;background:#D9A066;height:${Math.round(w.poop/max*118)}px"></div>
      <div style="width:14px;border-radius:6px 6px 0 0;background:#8FB8D0;height:${Math.round(w.pee/max*118)}px"></div>
    </div><div style="font-size:10.5px;color:#8A8378">${w.label}</div></div>`).join('');}
```

- [ ] **Step 4: 하단 네비 + 진입 동선** — v5 톤 하단탭(홈/기록/마이) + 홈 히어로 클릭→프로필, 마이/홈에서 **댕꾸·상점** 진입 버튼, 코인칩(`.coinval`)→상점. `go()`가 8개 화면·탭 활성표시 처리.

- [ ] **Step 5: 최종 전체 흐름 확인**

Run: `.venv/bin/python scripts/make_app.py && .venv/bin/python -m pytest -q`
브라우저(`http://localhost:8000`): 홈→경로(네이버지도)→산책(코인 줍기)→완료→댕꾸(옷)→상점(구매)→기록(그래프) 전 흐름 + 콘솔 무에러 + 새로고침 후 코인/옷 유지.
Expected: 전체 통과, 기존 pytest 그대로 green.

- [ ] **Step 6: 커밋**
```bash
git add scripts/make_app.py docs/app/index.html "docs/app/조심해야댕.html"
git commit -m "feat(app): 산책중/완료/프로필/기록(대변·소변) v5 + 네비·진입동선 완성"
```

---

## Self-Review

- **스펙 커버리지**: v5 리스타일(T1,4,6,11)·네이버 지도(T1,5)·걷는 강아지(T3)·코인 줍기(T7,10)·댕꾸(T8)·상점(T9)·대변소변(T11)·영속(T7)·에셋(T2) — 스펙 §3~9 전부 태스크 대응 ✓
- **플레이스홀더**: 마크업 태스크는 v5 소스 라인 참조 + 핵심 코드 제시(모호 지시 없음). 로직 태스크는 완전 코드 ✓
- **타입 일관성**: `renderMap(elId,routeIdx,opts)`·`clearOverlays(M)`·`dressedImg(b,o)`·`GAME`·`addCoins`·`COIN_TS`/`WALK_DUR` 태스크 간 시그니처 일치 ✓
- **주의**: `renderHome`의 `m.temp/shade_word` 등은 기존 DATA 필드 확인 후 사용(없으면 기존 renderHome이 쓰던 값 재사용). 네이버 지도 렌더 검증은 localhost:8000(등록 도메인) 필요.
