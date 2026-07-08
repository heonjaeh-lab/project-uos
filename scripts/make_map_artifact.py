"""data/demo/map_data.json → 대화형 자체완결 HTML 지도(Artifact용).

다중 경로(그늘/균형/최단) + 클릭 선택 + GPS 출발 자동매칭 + 시간별 위험지수.
외부 타일/CDN 없이 실제 OSM 도로망을 인라인 SVG로 그린다(CSP 안전).
출력: docs/오늘의경로_지도.html
"""
import json

SRC = "data/demo/map_data.json"
OUT = "docs/오늘의경로_지도.html"

with open(SRC, encoding="utf-8") as f:
    data = json.load(f)

HTML = r"""<style>
:root{
  --bg:#f5f4f0;--panel:#fff;--ink:#1a1c1a;--muted:#6b6f6a;--hair:#e4e2db;--street:#d8d5cd;
  --accent:#0f766e;--accent-weak:#d9efe9;
  --sunny:#e08a1e;--shade:#0f766e;--faint:#b9b6ad;
  --good:#16a34a;--warn:#d97706;--bad:#dc2626;
  --poi-hosp:#e11d48;--poi-toilet:#2563eb;--poi-park:#16a34a;--poi-water:#0891b2;--poi-shop:#d97706;
  --shadow:0 1px 3px rgba(0,0,0,.08),0 10px 30px rgba(0,0,0,.06);
}
@media (prefers-color-scheme:dark){:root{
  --bg:#12140f;--panel:#1b1e19;--ink:#eef0ea;--muted:#9aa093;--hair:#2b2f28;--street:#333831;
  --accent:#5eead4;--accent-weak:#14342f;--faint:#4a4f47;
  --sunny:#f0a94a;--shade:#5eead4;--shadow:0 1px 3px rgba(0,0,0,.4);
}}
:root[data-theme="light"]{--bg:#f5f4f0;--panel:#fff;--ink:#1a1c1a;--muted:#6b6f6a;--hair:#e4e2db;--street:#d8d5cd;--accent:#0f766e;--accent-weak:#d9efe9;--shade:#0f766e;--faint:#b9b6ad;}
:root[data-theme="dark"]{--bg:#12140f;--panel:#1b1e19;--ink:#eef0ea;--muted:#9aa093;--hair:#2b2f28;--street:#333831;--accent:#5eead4;--accent-weak:#14342f;--shade:#5eead4;--faint:#4a4f47;}
*{box-sizing:border-box}
.wrap{font-family:ui-sans-serif,-apple-system,"Apple SD Gothic Neo","Malgun Gothic",system-ui,sans-serif;
  background:var(--bg);color:var(--ink);padding:20px;max-width:960px;margin:0 auto;line-height:1.5}
.top{display:flex;flex-wrap:wrap;align-items:center;gap:12px;margin-bottom:12px}
.badge{display:flex;align-items:center;gap:11px;background:var(--panel);border:1px solid var(--hair);
  border-radius:14px;padding:11px 15px;box-shadow:var(--shadow)}
.score{font-size:28px;font-weight:800;font-variant-numeric:tabular-nums;line-height:1}
.sig{width:11px;height:11px;border-radius:50%}
.sig.green{background:var(--good)}.sig.yellow{background:var(--warn)}.sig.red{background:var(--bad)}
.ttl{font-size:14px;font-weight:700}.sub{font-size:12px;color:var(--muted)}
.chips{display:flex;gap:7px;flex-wrap:wrap;margin-left:auto}
.chip{background:var(--panel);border:1px solid var(--hair);border-radius:999px;padding:5px 11px;
  font-size:12px;color:var(--muted);font-variant-numeric:tabular-nums}.chip b{color:var(--ink)}
/* 산책 게이트 배너 */
.advisory{display:flex;align-items:center;gap:11px;border-radius:13px;padding:12px 16px;margin-bottom:12px;
  border:1.5px solid;box-shadow:var(--shadow)}
.advisory .ic{font-size:22px;line-height:1}
.advisory .txt{font-size:14px;font-weight:800}
.advisory .rs{font-size:12.5px;font-weight:600;opacity:.9}
.advisory.go{background:var(--accent-weak);border-color:var(--good);color:var(--ink)}
.advisory.caution{background:rgba(217,119,6,.12);border-color:var(--warn);color:var(--ink)}
.advisory.stop{background:rgba(220,38,38,.13);border-color:var(--bad);color:var(--ink)}
/* 시간별 위험지수 스트립 */
.hourly{background:var(--panel);border:1px solid var(--hair);border-radius:14px;padding:12px 14px 10px;
  box-shadow:var(--shadow);margin-bottom:12px}
.hourly h4{margin:0 0 9px;font-size:12.5px;color:var(--muted);font-weight:700;letter-spacing:.02em}
.hbars{display:flex;gap:6px;align-items:flex-end;overflow-x:auto;padding-bottom:2px}
.hbar{flex:1 0 40px;display:flex;flex-direction:column;align-items:center;gap:4px}
.hbar .b{width:100%;border-radius:5px 5px 3px 3px;min-height:8px}
.hbar .s{font-size:11px;font-variant-numeric:tabular-nums;color:var(--muted)}
.hbar .h{font-size:11px;color:var(--muted)}
.hbar.now .h{color:var(--ink);font-weight:800}
.hbar.now{position:relative}
.hbar.now::after{content:"지금";position:absolute;top:-14px;font-size:9.5px;color:var(--accent);font-weight:800}
/* 경로 선택 */
.routes{display:flex;gap:9px;flex-wrap:wrap;margin-bottom:12px}
.rcard{flex:1 1 150px;background:var(--panel);border:1.5px solid var(--hair);border-radius:13px;
  padding:11px 13px;cursor:pointer;transition:border-color .15s,transform .1s;text-align:left}
.rcard:hover{transform:translateY(-1px)}
.rcard.active{border-color:var(--accent);background:var(--accent-weak)}
.rcard .rl{font-size:13.5px;font-weight:800;display:flex;align-items:center;gap:6px}
.rcard .rl .swatch{width:14px;height:4px;border-radius:2px}
.rcard .rm{font-size:12px;color:var(--muted);margin-top:5px;font-variant-numeric:tabular-nums}
.rcard .rm b{color:var(--ink)}
.mapbox{background:var(--panel);border:1px solid var(--hair);border-radius:16px;padding:8px;box-shadow:var(--shadow);overflow:hidden}
svg{width:100%;height:auto;display:block;border-radius:10px}
.pulse{animation:pulse 2s ease-out infinite}
@keyframes pulse{0%{r:6;opacity:.9}70%{r:16;opacity:0}100%{opacity:0}}
@media (prefers-reduced-motion:reduce){.pulse{animation:none;opacity:0}}
.legend{display:flex;flex-wrap:wrap;gap:12px 18px;margin-top:11px;font-size:12px;color:var(--muted)}
.lg{display:flex;align-items:center;gap:6px}.dot{width:10px;height:10px;border-radius:50%}
.bar{width:24px;height:5px;border-radius:3px;background:linear-gradient(90deg,var(--sunny),var(--shade))}
.tip{position:fixed;pointer-events:none;background:var(--ink);color:var(--bg);font-size:12px;
  padding:5px 9px;border-radius:7px;opacity:0;transition:opacity .12s;white-space:nowrap;z-index:9}
.foot{font-size:11px;color:var(--muted);margin-top:11px;text-align:center}
</style>

<div class="wrap">
  <div class="top">
    <div class="badge"><div class="score" id="score">–</div>
      <div><div class="ttl">지금 산책 위험지수</div><div class="sub" id="sub">송파구 · 실측</div></div>
      <span class="sig" id="sig"></span></div>
    <div class="chips" id="chips"></div>
  </div>

  <div class="advisory" id="advisory"></div>

  <div class="hourly"><h4>시간별 위험지수 (실측 예보 기반 · 매시간 갱신)</h4><div class="hbars" id="hbars"></div></div>

  <div class="routes" id="routes"></div>

  <div class="mapbox"><svg id="map" xmlns="http://www.w3.org/2000/svg"></svg></div>

  <div class="legend">
    <span class="lg"><span class="bar"></span>선택 경로(햇볕→그늘)</span>
    <span class="lg"><span class="dot" style="background:var(--faint)"></span>다른 후보</span>
    <span class="lg"><span class="dot" style="background:var(--poi-hosp)"></span>동물병원</span>
    <span class="lg"><span class="dot" style="background:var(--poi-toilet)"></span>화장실</span>
    <span class="lg"><span class="dot" style="background:var(--poi-park)"></span>공원</span>
    <span class="lg">◉ 내 위치(GPS) · ▣ 도착</span>
  </div>
  <div class="foot">실 데이터: OSM 보행망·건물 그림자 · 기상청·에어코리아 실측 · 결정론 라우팅 (조심해야댕) · 경로 카드나 지도를 눌러 선택</div>
</div>
<div class="tip" id="tip"></div>

<script>
const DATA=__DATA__;
const NS="http://www.w3.org/2000/svg";
const [minLon,minLat,maxLon,maxLat]=DATA.bbox;
const cosf=Math.cos((minLat+maxLat)/2*Math.PI/180);
const W=1000,H=Math.round(W*(maxLat-minLat)/((maxLon-minLon)*cosf));
const px=lo=>(lo-minLon)/(maxLon-minLon)*W, py=la=>H-(la-minLat)/(maxLat-minLat)*H;
const map=document.getElementById("map");map.setAttribute("viewBox",`0 0 ${W} ${H}`);
const cs=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
function poly(pts,stroke,w,op,cls){const p=document.createElementNS(NS,"polyline");
  p.setAttribute("points",pts.map(c=>px(c[0])+","+py(c[1])).join(" "));p.setAttribute("fill","none");
  p.setAttribute("stroke",stroke);p.setAttribute("stroke-width",w);p.setAttribute("stroke-linecap","round");
  p.setAttribute("stroke-linejoin","round");if(op!=null)p.setAttribute("opacity",op);if(cls)p.setAttribute("class",cls);
  return p;}
function shadeColor(s){const a=[224,138,30],b=[15,118,110];return `rgb(${a.map((v,i)=>Math.round(v+(b[i]-v)*s)).join(",")})`;}

// 배경 도로망
const gCtx=document.createElementNS(NS,"g");map.appendChild(gCtx);
DATA.context.forEach(e=>gCtx.appendChild(poly(e,cs('--street'),1.1,.9)));
const gRoute=document.createElementNS(NS,"g");map.appendChild(gRoute);
const gPoi=document.createElementNS(NS,"g");map.appendChild(gPoi);
const gMark=document.createElementNS(NS,"g");map.appendChild(gMark);

const KOR={animal_hospital:"동물병원",toilet:"화장실",park:"공원",water_fountain:"급수대",pet_shop:"펫샵"};
const COL={animal_hospital:"--poi-hosp",toilet:"--poi-toilet",park:"--poi-park",water_fountain:"--poi-water",pet_shop:"--poi-shop"};
const tip=document.getElementById("tip");
let sel=0;

function drawRoutes(){
  gRoute.innerHTML="";gPoi.innerHTML="";
  // 비선택 경로(옅게)
  DATA.routes.forEach((rt,i)=>{if(i===sel)return;
    rt.segs.forEach(s=>{const p=poly(s.line,cs('--faint'),3,.85);
      p.style.cursor="pointer";p.addEventListener("click",()=>select(i));gRoute.appendChild(p);});});
  // 선택 경로(그늘색, 흰 테두리)
  const rt=DATA.routes[sel];
  rt.segs.forEach(s=>gRoute.appendChild(poly(s.line,cs('--panel'),7.5,1)));
  rt.segs.forEach(s=>gRoute.appendChild(poly(s.line,shadeColor(s.shade),4.5,1)));
  // 선택 경로 POI
  rt.pois.forEach(p=>{const c=document.createElementNS(NS,"circle");
    c.setAttribute("cx",px(p.lon));c.setAttribute("cy",py(p.lat));c.setAttribute("r",6);
    c.setAttribute("fill",`var(${COL[p.type]||'--accent'})`);c.setAttribute("stroke",cs('--panel'));c.setAttribute("stroke-width",2);
    c.style.cursor="pointer";
    c.addEventListener("mousemove",e=>{tip.style.opacity=1;tip.textContent=`${KOR[p.type]||p.type} · ${p.name}`;
      tip.style.left=(e.clientX+12)+"px";tip.style.top=(e.clientY+12)+"px";});
    c.addEventListener("mouseleave",()=>tip.style.opacity=0);gPoi.appendChild(c);});
}

// 마커: GPS 위치(펄스) + 도착
function mark(c,txt,fill,pulse){
  if(pulse){const r=document.createElementNS(NS,"circle");r.setAttribute("cx",px(c[0]));r.setAttribute("cy",py(c[1]));
    r.setAttribute("fill",fill);r.setAttribute("class","pulse");gMark.appendChild(r);}
  const bg=document.createElementNS(NS,"circle");bg.setAttribute("cx",px(c[0]));bg.setAttribute("cy",py(c[1]));
  bg.setAttribute("r",8.5);bg.setAttribute("fill",fill);bg.setAttribute("stroke",cs('--panel'));bg.setAttribute("stroke-width",2.5);
  const t=document.createElementNS(NS,"text");t.setAttribute("x",px(c[0]));t.setAttribute("y",py(c[1])+3.3);
  t.setAttribute("text-anchor","middle");t.setAttribute("font-size","9.5");t.setAttribute("font-weight","800");t.setAttribute("fill","#fff");
  t.textContent=txt;gMark.appendChild(bg);gMark.appendChild(t);}
function drawMarks(){gMark.innerHTML="";mark(DATA.gps?[DATA.gps.lon,DATA.gps.lat]:DATA.origin,"나",cs('--accent'),true);
  mark(DATA.dest,"착",cs('--ink'),false);}

// 경로 선택 카드
function drawCards(){const box=document.getElementById("routes");box.innerHTML="";
  DATA.routes.forEach((rt,i)=>{const d=document.createElement("div");d.className="rcard"+(i===sel?" active":"");
    d.innerHTML=`<div class="rl"><span class="swatch" style="background:${shadeColor(rt.shade)}"></span>${rt.label}</div>`+
      `<div class="rm">그늘 <b>${Math.round(rt.shade*100)}%</b> · <b>${(rt.distance_m/1000).toFixed(2)}km</b> · ${rt.est_time_min}분 · 안전지점 ${rt.pois.length}</div>`;
    d.addEventListener("click",()=>select(i));box.appendChild(d);});}

function select(i){sel=i;drawCards();drawRoutes();drawMarks();}

// 시간별 위험지수 스트립
function drawHourly(){const box=document.getElementById("hbars");box.innerHTML="";
  const sc={green:'--good',yellow:'--warn',red:'--bad'};
  DATA.hourly.forEach((h,i)=>{const w=document.createElement("div");w.className="hbar"+(i===0?" now":"");
    const ht=18+h.score*0.9;
    w.innerHTML=`<div class="s">${h.score}</div><div class="b" style="height:${ht}px;background:var(${sc[h.level]||'--good'})"></div><div class="h">${h.hour}시</div>`;
    box.appendChild(w);});}

// 헤더
const m=DATA.meta;
document.getElementById("score").textContent=m.now_score??"–";
document.getElementById("sig").className="sig "+(m.now_level||"green");
document.getElementById("sub").textContent=`송파구 · 주요인 ${m.now_dominant||"-"} · 실측`;
document.getElementById("chips").innerHTML=
  `<span class="chip">기온 <b>${m.air_temp_c}℃</b></span><span class="chip">습도 <b>${m.humidity_pct}%</b></span><span class="chip">PM10 <b>${m.pm10}</b></span>`+
  (m.precip_prob_pct!=null?`<span class="chip">강수확률 <b>${Math.round(m.precip_prob_pct)}%</b></span>`:``);

// 산책 게이트 배너 (비 오면 STOP)
const AD={go:{ic:"🐾",t:"지금 산책하기 좋아요"},caution:{ic:"⚠️",t:"주의가 필요해요"},stop:{ic:"🚫",t:"지금은 산책을 미뤄주세요"}};
const ad=AD[m.advisory]||AD.go;const ab=document.getElementById("advisory");
ab.className="advisory "+(m.advisory||"go");
ab.innerHTML=`<span class="ic">${ad.ic}</span><div><div class="txt">${ad.t}</div><div class="rs">${m.advisory_reason||""}</div></div>`;

drawHourly();select(0);
</script>
"""

out = HTML.replace("__DATA__", json.dumps(data, ensure_ascii=False))
with open(OUT, "w", encoding="utf-8") as f:
    f.write(out)
print(f"wrote {OUT} ({len(out)} bytes)")
