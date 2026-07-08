"""data/demo/map_data.json → docs/app/조심해야댕.html (작동 앱 프로토타입).

디자인('안전한 산책 동반자' 1a 신호등 히어로)을 1:1 재현하되, 하드코딩 mock이 아니라
실제 엔진 데이터(위험지수·시간별·다중경로·그늘·POI·비 게이트)로 구동한다.
홈 → 경로(다중 선택) → 산책중(리라우팅) → 완료 플로우. 표준 HTML/CSS/JS.
"""
import json

SRC = "data/demo/map_data.json"
OUT = "docs/app/조심해야댕.html"
with open(SRC, encoding="utf-8") as f:
    DATA = json.load(f)

HTML = r"""<!DOCTYPE html><html lang="ko"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>조심해야댕</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Jua&family=Gothic+A1:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
body{margin:0;background:#F1EBE0;font-family:'Gothic A1',sans-serif;display:flex;justify-content:center;
  align-items:flex-start;padding:24px 12px;min-height:100vh}
.phone{width:392px;height:848px;background:#FFFDFA;border-radius:44px;overflow:hidden;position:relative;
  box-shadow:0 24px 60px rgba(120,80,40,.22),0 4px 14px rgba(120,80,40,.12);border:7px solid #fff}
.scr{position:absolute;inset:0;display:none;flex-direction:column;background:#FFFDFA}
.scr.on{display:flex}
.stbar{height:42px;flex:none;display:flex;align-items:center;justify-content:space-between;padding:0 26px;
  font-weight:800;font-size:14px;color:#2E2A27}
.stbar .notch{width:16px;height:9px;border:1.5px solid #2E2A27;border-radius:2px}
.body{flex:1;overflow-y:auto;overflow-x:hidden}
.cta{flex:none;padding:12px 22px 20px;background:linear-gradient(rgba(255,253,250,0),#FFFDFA 34%)}
.btn{width:100%;border:none;height:54px;border-radius:18px;background:#F1592A;color:#fff;font-family:'Gothic A1';
  font-weight:800;font-size:17px;cursor:pointer;box-shadow:0 8px 22px rgba(241,89,42,.32);transition:transform .12s}
.btn:active{transform:translateY(1px)}
.btn.dark{background:#2E2A27;box-shadow:0 8px 20px rgba(46,42,39,.28)}
.btn.disabled{background:#D9CFC1;box-shadow:none;cursor:not-allowed}
.icobtn{width:40px;height:40px;border-radius:14px;border:none;background:#F6EEE2;display:flex;align-items:center;justify-content:center;cursor:pointer}
.brand{font-family:'Jua';font-size:26px;color:#F1592A;letter-spacing:-1px}
.avatar{width:42px;height:42px;border-radius:50%;overflow:hidden;background:#F6EEE2;flex:none}
.avatar img{width:100%;height:100%;object-fit:cover;transform:scale(2.1);transform-origin:40% 34%}
.num{font-family:'Jua'}
.chip{background:#FFF7EE;border:1.5px solid #F4E7D5;border-radius:14px;padding:8px 6px;text-align:center}
.chip .k{font-weight:700;font-size:10.5px;color:#9A928B}.chip .v{font-weight:800;font-size:14px;color:#2E2A27;margin-top:1px}
.card{border-radius:20px;overflow:hidden;border:1.5px solid #F0E4D2;background:#fff;box-shadow:0 6px 16px rgba(150,110,60,.07)}
/* 신호등 히어로 */
.hero{margin-top:6px;background:linear-gradient(160deg,#FFEACF,#FDE0CF);border-radius:20px;padding:12px 16px 14px;position:relative;overflow:hidden}
.hero.lv-green{background:linear-gradient(160deg,#E4F5E6,#D6EFDA)}
.hero.lv-red{background:linear-gradient(160deg,#FBE0DC,#F6D0CB)}
.tl{position:absolute;top:12px;right:12px;display:flex;flex-direction:column;gap:4px;padding:6px 5px;background:#3A2E25;border-radius:12px}
.tl span{width:8px;height:8px;border-radius:50%}
.ring{width:96px;height:96px;border-radius:50%;display:flex;align-items:center;justify-content:center;margin:2px auto 0;box-shadow:0 8px 16px rgba(220,150,40,.22)}
.ring .inner{width:72px;height:72px;border-radius:50%;background:#fff;display:flex;flex-direction:column;align-items:center;justify-content:center}
.ring .sc{font-family:'Jua';font-size:29px;color:#2E2A27;line-height:1}
.ring .lb{font-weight:800;font-size:10px;letter-spacing:.5px}
/* 시간별 스트립 */
.hrow{display:flex;gap:5px;overflow-x:auto;padding-bottom:2px}
.hcell{flex:1 0 34px;display:flex;flex-direction:column;align-items:center;gap:3px}
.hcell .hb{width:100%;border-radius:5px 5px 3px 3px;min-height:6px}
.hcell .hs{font-size:10px;font-weight:700;color:#9A928B;font-variant-numeric:tabular-nums}
.hcell .hh{font-size:9.5px;color:#9A928B}
.hcell.now .hh{color:#F1592A;font-weight:800}
/* 게이트 배너 */
.gate{display:flex;align-items:center;gap:11px;border-radius:16px;padding:12px 15px;border:1.5px solid}
.gate .ic{font-size:20px}.gate .t{font-weight:800;font-size:14px;color:#2E2A27}.gate .r{font-weight:600;font-size:12px;color:#7d6a56}
.gate.go{background:#E4F4F1;border-color:#8fd6cc}.gate.caution{background:#FBEEDD;border-color:#F3B23A}
.gate.stop{background:#FBE0DC;border-color:#EE5140}
/* 경로 칩 */
.rchip{flex:1;border:1.5px solid #E9DCC9;background:#fff;border-radius:14px;padding:9px 6px;cursor:pointer;text-align:center;transition:.12s}
.rchip.on{border-color:#F1592A;background:#FDEDE4}
.rchip .rl{font-weight:800;font-size:12.5px;color:#2E2A27}.rchip .rm{font-weight:700;font-size:10.5px;color:#9A928B;margin-top:2px}
.poi{display:flex;align-items:center;gap:12px;background:#fff;border:1.5px solid #F1E6D7;border-radius:16px;padding:11px 13px}
.poi .pic{width:34px;height:34px;border-radius:11px;display:flex;align-items:center;justify-content:center;flex:none}
.mapwrap{border-radius:18px;overflow:hidden;position:relative;background:#F3EEE3}
.legend{position:absolute;top:10px;left:10px;display:flex;align-items:center;gap:6px;background:rgba(255,255,255,.92);
  padding:5px 10px;border-radius:999px;box-shadow:0 3px 10px rgba(90,60,30,.12);font-weight:700;font-size:11px;color:#5a4a3a}
.demo{position:absolute;bottom:10px;right:10px;background:rgba(255,255,255,.92);border:1px solid #E9DCC9;border-radius:999px;
  padding:5px 10px;font-size:11px;font-weight:700;color:#7d6a56;cursor:pointer;z-index:6;box-shadow:0 2px 8px rgba(90,60,30,.12)}
@keyframes pulse{0%{transform:scale(1);opacity:.5}70%{transform:scale(2.6);opacity:0}100%{opacity:0}}
@keyframes toastin{from{opacity:0;transform:translateY(-8px)}to{opacity:1;transform:translateY(0)}}
@keyframes popin{from{opacity:0;transform:scale(.92)}to{opacity:1;transform:scale(1)}}
</style></head><body>
<div class="phone">
  <!-- ===== HOME ===== -->
  <div class="scr on" id="s-home">
    <div class="stbar"><span>9:41</span><span class="notch"></span></div>
    <div class="body" style="padding:4px 22px 18px">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
        <span class="brand">조심해야댕</span>
        <div class="avatar"><img src="assets/mandu.png" alt="만두"></div>
      </div>
      <div style="height:78px;display:flex;align-items:flex-end;justify-content:center">
        <img src="assets/dog-walk.png" style="width:78px;height:78px;object-fit:contain"></div>

      <div class="hero" id="hero">
        <div class="tl" id="tl"><span data-l="red"></span><span data-l="yellow"></span><span data-l="green"></span></div>
        <div class="ring" id="ring"><div class="inner"><span class="sc" id="heroScore">–</span><span class="lb" id="heroLabel"></span></div></div>
        <div style="text-align:center;margin-top:7px">
          <div style="font-weight:800;font-size:15px;color:#2E2A27" id="heroMsg"></div>
          <div style="font-weight:500;font-size:12px;color:#7d6a56;margin-top:2px" id="heroSub"></div>
        </div>
      </div>

      <div style="margin-top:8px;display:flex;gap:7px" id="chips"></div>

      <div style="margin-top:14px;font-weight:800;font-size:13px;color:#2E2A27">시간별 위험지수 <span style="font-weight:600;color:#9A928B;font-size:11px">· 매시간</span></div>
      <div class="hrow" id="hrow" style="margin-top:8px"></div>

      <div style="margin-top:14px" id="gate"></div>
      <div style="margin-top:9px;text-align:center">
        <button id="rainToggle" onclick="toggleRain()" style="border:1px dashed #C9BBA8;background:transparent;border-radius:999px;padding:5px 12px;font-size:11px;font-weight:700;color:#9A928B;cursor:pointer;font-family:'Gothic A1'">🌧️ 비 오는 날이면? (미리보기)</button>
      </div>

      <div style="margin-top:16px;font-weight:800;font-size:13px;color:#2E2A27">오늘의 추천 산책길</div>
      <div class="card" style="margin-top:8px" onclick="go('route')">
        <div class="mapwrap" style="height:96px;border-radius:0" id="homeMap"></div>
        <div style="padding:12px 15px;display:flex;align-items:center;justify-content:space-between">
          <div><div style="font-weight:900;font-size:15px;color:#2E2A27" id="homeRouteName"></div>
            <div style="font-weight:600;font-size:12px;color:#9A928B;margin-top:2px" id="homeRouteMeta"></div></div>
          <span style="display:flex;align-items:center;gap:6px;font-weight:800;font-size:12.5px;color:#1c8a7e;background:#E4F4F1;padding:6px 11px;border-radius:999px"><span style="width:10px;height:10px;border-radius:50%;background:#35B36B"></span>안전</span>
        </div>
      </div>
    </div>
    <div class="cta"><button class="btn" id="homeCta" onclick="go('route')">안전한 길 찾기</button></div>
  </div>

  <!-- ===== ROUTE ===== -->
  <div class="scr" id="s-route">
    <div class="stbar"><span>9:41</span><span class="notch"></span></div>
    <div style="flex:none;display:flex;align-items:center;gap:12px;padding:2px 20px 12px">
      <button class="icobtn" onclick="go('home')"><svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="#2E2A27" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M15 5l-7 7 7 7"></path></svg></button>
      <span style="font-weight:900;font-size:19px;color:#2E2A27">안전한 길</span>
      <span style="margin-left:auto;font-weight:800;font-size:12.5px;color:#C24E24;background:#FBE7DB;padding:6px 12px;border-radius:999px">만두 · 말티즈</span>
    </div>
    <div class="body" style="padding:0 20px 20px">
      <div style="font-weight:700;font-size:12px;color:#9A928B;margin-bottom:8px">📍 내 위치(GPS)에서 · 추천 3개 중 골라</div>
      <div style="display:flex;gap:8px;margin-bottom:12px" id="rchips"></div>
      <div class="mapwrap" style="height:200px" id="routeMap"></div>
      <div class="card" style="margin-top:14px;border-radius:22px;padding:16px 18px">
        <div style="display:flex;align-items:center;justify-content:space-between">
          <span style="font-weight:900;font-size:18px;color:#2E2A27" id="rName"></span>
          <span style="display:flex;align-items:center;gap:6px;font-weight:800;font-size:13px;color:#2E2A27;background:#F6EEE2;padding:6px 12px;border-radius:999px"><span id="rMaxDot" style="width:11px;height:11px;border-radius:50%"></span>최대 <span id="rMaxLabel"></span></span>
        </div>
        <div style="display:flex;margin-top:14px">
          <div style="flex:1;text-align:center"><div class="num" style="font-size:20px;color:#2E2A27" id="rDist"></div><div style="font-weight:700;font-size:11px;color:#9A928B">거리</div></div>
          <div style="flex:1;text-align:center;border-left:1px solid #F0E6D6"><div class="num" style="font-size:20px;color:#2E2A27" id="rTime"></div><div style="font-weight:700;font-size:11px;color:#9A928B">예상 시간</div></div>
          <div style="flex:1;text-align:center;border-left:1px solid #F0E6D6"><div class="num" style="font-size:20px;color:#26A99B" id="rShade"></div><div style="font-weight:700;font-size:11px;color:#9A928B">평균 그늘</div></div>
          <div style="flex:1;text-align:center;border-left:1px solid #F0E6D6"><div class="num" style="font-size:20px;color:#2E2A27" id="rSafe"></div><div style="font-weight:700;font-size:11px;color:#9A928B">안전지점</div></div>
        </div>
        <div style="display:flex;gap:8px;align-items:flex-start;margin-top:14px;background:#FBF4E9;border-radius:14px;padding:11px 12px">
          <span style="font-size:15px">🐾</span><span style="font-weight:600;font-size:13px;color:#6b5d4f;line-height:1.5" id="rNote"></span>
        </div>
      </div>
      <div style="margin-top:16px;font-weight:800;font-size:13px;color:#9A928B">경로 위 안전 지점</div>
      <div style="margin-top:10px;display:flex;flex-direction:column;gap:9px" id="poiList"></div>
    </div>
    <div class="cta"><button class="btn" onclick="go('walk')">이 길로 산책 시작</button></div>
  </div>

  <!-- ===== WALKING ===== -->
  <div class="scr" id="s-walk">
    <div class="stbar"><span>9:41</span><span class="notch"></span></div>
    <div style="flex:none;display:flex;align-items:center;gap:12px;padding:2px 20px 10px">
      <span style="width:9px;height:9px;border-radius:50%;background:#F1592A;box-shadow:0 0 0 4px rgba(241,89,42,.18)"></span>
      <span style="font-weight:900;font-size:19px;color:#2E2A27">산책 중</span>
      <span style="margin-left:auto;font-weight:800;font-size:12.5px;color:#26A99B;background:#E4F4F1;padding:6px 12px;border-radius:999px">안전하게 걷는 중</span>
    </div>
    <div class="body" style="padding:0 20px 20px">
      <div id="rerouteAlert"></div>
      <button id="tipBtn" style="width:100%;text-align:left;border:none;cursor:pointer;background:linear-gradient(120deg,#F1592A,#F5813F);border-radius:20px;padding:15px 17px;box-shadow:0 8px 20px rgba(241,89,42,.28);animation:toastin .35s ease;display:flex;align-items:center;gap:12px;margin-top:4px">
        <span style="font-size:20px">🐾</span>
        <span style="flex:1;font-weight:800;font-size:14px;color:#fff;line-height:1.45" id="tipText"></span>
        <span style="font-weight:800;font-size:12px;color:rgba(255,255,255,.85)">다음 →</span>
      </button>
      <div class="mapwrap" style="margin-top:14px;height:150px" id="walkMap"></div>
      <div style="margin-top:16px;display:flex;align-items:flex-end;justify-content:space-between">
        <div><div style="font-weight:700;font-size:12px;color:#9A928B">지난 시간</div><div class="num" style="font-size:36px;color:#2E2A27;line-height:1">12:30</div></div>
        <div style="text-align:right"><div style="font-weight:700;font-size:12px;color:#9A928B">걸은 거리</div><div class="num" style="font-size:36px;color:#F1592A;line-height:1" id="walkDist">0.6km</div></div>
      </div>
      <div style="margin-top:10px;height:11px;background:#F1E6D7;border-radius:999px;overflow:hidden"><div style="height:100%;background:linear-gradient(90deg,#F1592A,#F5A623);border-radius:999px;width:42%"></div></div>
      <div style="margin-top:14px;display:flex;align-items:center;gap:10px;background:#E4F4F1;border-radius:16px;padding:13px 15px"><span style="font-size:18px">🌳</span><div><div style="font-weight:800;font-size:14px;color:#1c8a7e">지금 그늘 구간</div><div style="font-weight:600;font-size:12.5px;color:#4a8a82">발바닥이 시원해서 좋아</div></div></div>
    </div>
    <div class="cta"><button class="btn dark" onclick="go('done')">산책 끝내기</button></div>
  </div>

  <!-- ===== DONE overlay ===== -->
  <div class="scr" id="s-done" style="background:rgba(46,42,39,.4);align-items:center;justify-content:center;padding:24px">
    <div style="background:#fff;border-radius:28px;padding:30px 26px;text-align:center;width:100%;animation:popin .3s ease">
      <div style="width:74px;height:74px;border-radius:50%;background:#E4F4F1;display:flex;align-items:center;justify-content:center;margin:0 auto"><svg width="38" height="38" viewBox="0 0 24 24" fill="none" stroke="#26A99B" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M5 13l4 4 10-11"></path></svg></div>
      <div class="num" style="font-size:24px;color:#2E2A27;margin-top:16px">잘했어, 만두!</div>
      <div style="font-weight:600;font-size:14px;color:#7d6a56;margin-top:5px;line-height:1.5">오늘도 안전하게 다녀왔어.<br>발바닥도 시원했지?</div>
      <div style="display:flex;margin-top:20px;background:#FBF4E9;border-radius:16px;padding:14px 0" id="doneStats"></div>
      <button class="btn" style="margin-top:20px" onclick="go('home')">홈으로</button>
    </div>
  </div>
</div>

<script>
const DATA=__DATA__;
let sel=0, rainDemo=false;
const SIG={green:'#35B36B',yellow:'#F3B23A',red:'#EE5140'};
const LVLABEL={green:'좋음',yellow:'주의',red:'위험'};
const $=id=>document.getElementById(id);
function go(s){for(const el of document.querySelectorAll('.scr'))el.classList.remove('on');
  $('s-'+s).classList.add('on');$('s-'+s).querySelector('.body')?.scrollTo(0,0);
  if(s==='route')renderRoute();if(s==='walk')renderWalk();if(s==='done')renderDone();}

// ---- 지도 렌더 (실제 경로 지오메트리, 파스텔 스타일) ----
function shadeColor(s){const a=[239,158,34],b=[38,169,155];return `rgb(${a.map((v,i)=>Math.round(v+(b[i]-v)*s)).join(',')})`;}
function renderMap(elId,routeIdx,showPos){
  const el=$(elId);const [mnx,mny,mxx,mxy]=DATA.bbox;const cf=Math.cos((mny+mxy)/2*Math.PI/180);
  const W=320,H=el.clientHeight||200;const vb=`0 0 ${W} ${H}`;
  const px=lo=>(lo-mnx)/(mxx-mnx)*W, py=la=>H-(la-mny)/(mxy-mny)*H;
  let svg=`<svg viewBox="${vb}" preserveAspectRatio="xMidYMid slice" style="width:100%;height:100%;display:block"><rect width="${W}" height="${H}" fill="#F3EEE3"/>`;
  svg+=`<ellipse cx="${W*.2}" cy="${H*.3}" rx="70" ry="48" fill="#E4EFD3"/><ellipse cx="${W*.8}" cy="${H*.8}" rx="76" ry="52" fill="#E4EFD3"/>`;
  for(const e of DATA.context.slice(0,240)){svg+=`<polyline points="${e.map(c=>px(c[0])+','+py(c[1])).join(' ')}" fill="none" stroke="#EAE2D2" stroke-width="3" stroke-linecap="round"/>`;}
  const rt=DATA.routes[routeIdx];
  for(const sg of rt.segs){const pts=sg.line.map(c=>px(c[0])+','+py(c[1])).join(' ');
    svg+=`<polyline points="${pts}" fill="none" stroke="#fff" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/>`;}
  for(const sg of rt.segs){const pts=sg.line.map(c=>px(c[0])+','+py(c[1])).join(' ');
    svg+=`<polyline points="${pts}" fill="none" stroke="${shadeColor(sg.shade)}" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>`;}
  for(const p of rt.pois){svg+=`<g transform="translate(${px(p.lon)},${py(p.lat)})"><circle r="6.5" fill="#fff" stroke="${poiColor(p.type)}" stroke-width="2.5"/><circle r="2.6" fill="${poiColor(p.type)}"/></g>`;}
  const g=DATA.gps;svg+=`<g transform="translate(${px(g.lon)},${py(g.lat)})"><circle r="9" fill="#F1592A" opacity=".28" style="transform-origin:center;animation:pulse 2s ease-out infinite"/><circle r="6" fill="#F1592A" stroke="#fff" stroke-width="2.5"/></g>`;
  const d=DATA.dest;svg+=`<g transform="translate(${px(d[0])},${py(d[1])})"><circle r="7" fill="#2E2A27" stroke="#fff" stroke-width="2.5"/></g>`;
  svg+=`</svg>`;
  const avg=Math.round(rt.shade*100);
  el.innerHTML=svg+`<div class="legend"><span style="width:9px;height:9px;border-radius:3px;background:#26A99B"></span>그늘 ${avg}% · ${rt.label}</div>`;
}
function poiColor(t){return {animal_hospital:'#EF5350',toilet:'#2F9BD6',park:'#7BAE3C',water_fountain:'#2F9BD6',pet_shop:'#EF9E22'}[t]||'#F1592A';}
const POI_KO={animal_hospital:'동물병원',toilet:'공중화장실',park:'공원',water_fountain:'급수대',pet_shop:'펫샵'};
const POI_SUB={animal_hospital:'응급 시 안심',toilet:'잠깐 쉬어가기',park:'뛰어놀기 좋아',water_fountain:'물 마시기 좋아',pet_shop:'간식 챙기기'};
function poiIconBg(t){return {animal_hospital:'#FCE9E8',toilet:'#E6F2FA',park:'#EDF4E2',water_fountain:'#E6F2FA',pet_shop:'#FBEEDD'}[t]||'#F6EEE2';}
function haversine(la1,lo1,la2,lo2){const R=6371000,r=Math.PI/180;const dp=(la2-la1)*r,dl=(lo2-lo1)*r;
  const a=Math.sin(dp/2)**2+Math.cos(la1*r)*Math.cos(la2*r)*Math.sin(dl/2)**2;return 2*R*Math.asin(Math.sqrt(a));}

// ---- 홈 ----
function advisoryView(){
  if(rainDemo)return {status:'stop',rain:true,reason:'지금 비가 와요 (2.5mm). 산책을 미뤄주세요.'};
  return {status:DATA.meta.advisory||'go',rain:DATA.meta.rain,reason:DATA.meta.advisory_reason||''};
}
function renderHome(){
  const m=DATA.meta;const adv=advisoryView();
  const lv=rainDemo?'red':m.now_level;const score=rainDemo?'—':m.now_score;
  const pct=rainDemo?100:Math.min(m.now_score,100);
  $('ring').style.background=`conic-gradient(${SIG[lv]} 0% ${pct}%,#F1E6D7 ${pct}% 100%)`;
  $('heroScore').textContent=score;
  $('heroLabel').textContent=LVLABEL[lv];$('heroLabel').style.color=SIG[lv];
  $('hero').className='hero lv-'+lv;
  for(const s of $('tl').children){const on=s.dataset.l===lv;s.style.background=SIG[s.dataset.l];
    s.style.opacity=on?1:.22;s.style.boxShadow=on?`0 0 8px ${SIG[s.dataset.l]}`:'none';}
  const MSG={green:'지금 나가기 좋아!',yellow:'오늘은 조금 더워.',red:'지금은 실내가 안전해.'};
  $('heroMsg').textContent=rainDemo?'비가 와서 오늘은 쉬자.':MSG[lv];
  $('heroSub').textContent=adv.reason;
  // 환경 칩 (실측)
  const pm=m.pm10, pmL=pm<=30?'좋음':pm<=80?'보통':'나쁨';
  $('chips').innerHTML=[['기온',Math.round(m.air_temp_c)+'°'],['습도',Math.round(m.humidity_pct)+'%'],
    ['미세먼지',pmL],['강수확률',Math.round(m.precip_prob_pct||0)+'%']]
    .map(([k,v])=>`<div class="chip" style="flex:1"><div class="k">${k}</div><div class="v">${v}</div></div>`).join('');
  // 시간별 스트립
  $('hrow').innerHTML=DATA.hourly.map((h,i)=>{const col=h.rain?'#2F9BD6':SIG[h.level];
    return `<div class="hcell ${i===0?'now':''}"><div class="hs">${h.rain?'☔':h.score}</div><div class="hb" style="height:${16+h.score*.55}px;background:${col}"></div><div class="hh">${+h.hour}시</div></div>`;}).join('');
  // 게이트
  const G={go:['🐾','산책하기 좋아요'],caution:['⚠️','주의가 필요해요'],stop:['🚫','지금은 산책 금지']};
  const gv=G[adv.status];
  $('gate').innerHTML=`<div class="gate ${adv.status}"><span class="ic">${gv[0]}</span><div style="flex:1"><div class="t">${gv[1]}</div><div class="r">${adv.reason}</div></div></div>`;
  // 홈 추천 경로(최고 그늘)
  const top=DATA.routes[0];
  $('homeRouteName').textContent=top.label+' 코스';
  $('homeRouteMeta').textContent=`${(top.distance_m/1000).toFixed(1)}km · ${Math.round(top.est_time_min)}분 · 그늘 ${Math.round(top.shade*100)}%`;
  renderMap('homeMap',0,false);
  // 비 오면 CTA 막기
  const cta=$('homeCta');
  if(adv.status==='stop'){cta.classList.add('disabled');cta.textContent='오늘은 산책을 쉬어요';cta.onclick=null;}
  else{cta.classList.remove('disabled');cta.textContent='안전한 길 찾기';cta.onclick=()=>go('route');}
}

// ---- 경로 ----
function renderRoute(){
  $('rchips').innerHTML=DATA.routes.map((r,i)=>`<div class="rchip ${i===sel?'on':''}" onclick="selectRoute(${i})"><div class="rl">${r.label}</div><div class="rm">그늘 ${Math.round(r.shade*100)}% · ${(r.distance_m/1000).toFixed(1)}km</div></div>`).join('');
  const r=DATA.routes[sel];
  $('rName').textContent=r.label+' 코스';
  $('rMaxDot').style.background=SIG[r.max_risk]||SIG.green;$('rMaxLabel').textContent=LVLABEL[r.max_risk]||'좋음';
  $('rDist').textContent=(r.distance_m/1000).toFixed(2)+'km';
  $('rTime').textContent=Math.round(r.est_time_min)+'분';
  $('rShade').textContent=Math.round(r.shade*100)+'%';
  $('rSafe').textContent=r.pois.length+'곳';
  const sp=Math.round(r.shade*100);
  $('rNote').textContent=sp>=70?`그늘이 ${sp}%라 발바닥이 시원해. 저녁 산책에 딱 좋아!`:sp>=50?`그늘 ${sp}%로 적당히 시원해. 물 자주 마시자.`:`그늘이 ${sp}%로 적어 햇볕이 많아. 짧게 다녀오자.`;
  const g=DATA.gps;
  $('poiList').innerHTML=r.pois.length?r.pois.map(p=>{const d=Math.round(haversine(g.lat,g.lon,p.lat,p.lon)/10)*10;
    return `<div class="poi"><span class="pic" style="background:${poiIconBg(p.type)}"><span style="width:15px;height:15px;border-radius:50%;background:${poiColor(p.type)}"></span></span><div style="flex:1"><div style="font-weight:800;font-size:14px;color:#2E2A27">${POI_KO[p.type]||p.type}</div><div style="font-weight:600;font-size:12px;color:#9A928B">${d}m · ${POI_SUB[p.type]||''}</div></div></div>`;}).join(''):'<div style="color:#9A928B;font-size:12.5px;padding:4px 2px">이 경로 주변 등록된 안전지점이 없어요.</div>';
  renderMap('routeMap',sel,false);
}
function selectRoute(i){sel=i;renderRoute();}

// ---- 산책중 ----
const TIPS=['지금은 그늘 구간이야. 천천히 걷자 🌳','앞쪽 급수대에서 물 한 모금 어때?','만두 발바닥 뜨겁지 않은지 확인해줘'];
let tipI=0;
function renderWalk(){
  renderMap('walkMap',sel,true);
  $('tipText').textContent=TIPS[0];tipI=0;
  $('tipBtn').onclick=()=>{tipI=(tipI+1)%TIPS.length;$('tipText').textContent=TIPS[tipI];};
  $('walkDist').textContent=(DATA.routes[sel].distance_m/1000*0.42).toFixed(1)+'km';
  // 동적 리라우팅 알림 (실제 M4 기능 시연)
  $('rerouteAlert').innerHTML=`<div style="display:flex;align-items:center;gap:10px;background:#FFF3E6;border:1.5px solid #F3B23A;border-radius:16px;padding:12px 14px;margin-top:4px;animation:toastin .35s ease"><span style="font-size:18px">🚧</span><div style="flex:1"><div style="font-weight:800;font-size:13.5px;color:#2E2A27">앞쪽 공사로 경로를 바꿨어요</div><div style="font-weight:600;font-size:12px;color:#9A928B">공사 구간 1곳 회피 · +120m 우회</div></div></div>`;
}

// ---- 완료 ----
function renderDone(){const r=DATA.routes[sel];
  $('doneStats').innerHTML=[['거리',(r.distance_m/1000).toFixed(1)+'km'],['시간',Math.round(r.est_time_min)+'분'],['그늘',Math.round(r.shade*100)+'%']]
    .map(([k,v],i)=>`<div style="flex:1;text-align:center;${i?'border-left:1px solid #EEE1CF':''}"><div class="num" style="font-size:19px;color:${k==='그늘'?'#26A99B':'#2E2A27'}">${v}</div><div style="font-weight:700;font-size:11px;color:#9A928B">${k}</div></div>`).join('');
}
function toggleRain(){rainDemo=!rainDemo;
  $('rainToggle').textContent=rainDemo?'☀️ 맑은 날로 되돌리기':'🌧️ 비 오는 날이면? (미리보기)';
  renderHome();}
renderHome();
</script>
</body></html>
"""

out = HTML.replace("__DATA__", json.dumps(DATA, ensure_ascii=False))
for path in (OUT, "docs/app/index.html"):   # index.html = 서빙/Pages 진입점
    with open(path, "w", encoding="utf-8") as f:
        f.write(out)
print(f"wrote {OUT} + index.html ({len(out)} bytes)")
