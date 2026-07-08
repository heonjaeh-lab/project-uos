"""기상·대기질 실데이터 어댑터 (공공데이터포털, DATA_GO_KR_KEY 필요).

- 에어코리아 대기오염정보: 송파구 측정소 PM10/PM2.5 (실측).
- 기상청 단기예보: 송파(nx=62,ny=126) 기온·습도·풍속 (예보).
→ engine.schemas.EnvObservation 으로 합쳐 위험지수(M2) 입력으로 쓴다.

미제공(키 미승인/무소스): 자외선(UV, data.go.kr 활용신청 필요) · 노면온도(RWIS 없음)
→ `build_songpa_env`가 이들을 `missing` 집합으로 표시해 compute_risk가 중립 처리한다.
키가 없으면 예외 대신 None/mock 폴백(엔진은 죽지 않는다).
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import requests

from engine.schemas import EnvObservation, Season
from engine.sources import config

SEOUL = ZoneInfo("Asia/Seoul")
SONGPA_NX, SONGPA_NY = 62, 126           # 기상청 격자 좌표(송파구)
SONGPA_CENTER = (37.5145, 127.1059)
AIR_STATION = "송파구"

_AIR_URL = "http://apis.data.go.kr/B552584/ArpltnInforInqireSvc/getCtprvnRltmMesureDnsty"
_FCST_URL = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
_BASE_TIMES = ["2300", "2000", "1700", "1400", "1100", "0800", "0500", "0200"]


def _season(month: int) -> Season:
    if month in (6, 7, 8):
        return Season.summer
    if month in (12, 1, 2):
        return Season.winter
    return Season.shoulder


def latlon_to_grid(lat: float, lon: float) -> tuple[int, int]:
    """WGS84 → 기상청 단기예보 격자(nx, ny). LCC 투영(기상청 공식).

    임의 서울/전국 좌표에서 그 지점의 예보를 받기 위해 사용한다.
    (송파 중심 ≈ (62, 126)이 되도록 검증.)
    """
    import math
    RE, GRID = 6371.00877, 5.0
    SLAT1, SLAT2, OLON, OLAT, XO, YO = 30.0, 60.0, 126.0, 38.0, 43, 136
    D = math.pi / 180.0
    re = RE / GRID
    s1, s2, ol, oa = SLAT1 * D, SLAT2 * D, OLON * D, OLAT * D
    sn = math.log(math.cos(s1) / math.cos(s2)) / math.log(
        math.tan(math.pi * 0.25 + s2 * 0.5) / math.tan(math.pi * 0.25 + s1 * 0.5))
    sf = math.pow(math.tan(math.pi * 0.25 + s1 * 0.5), sn) * math.cos(s1) / sn
    ro = re * sf / math.pow(math.tan(math.pi * 0.25 + oa * 0.5), sn)
    ra = re * sf / math.pow(math.tan(math.pi * 0.25 + lat * D * 0.5), sn)
    theta = lon * D - ol
    theta = (theta + math.pi) % (2 * math.pi) - math.pi
    theta *= sn
    nx = int(ra * math.sin(theta) + XO + 0.5)
    ny = int(ro - ra * math.cos(theta) + YO + 0.5)
    return nx, ny


def fetch_air_quality(station: str = AIR_STATION) -> dict | None:
    """송파구 측정소 실시간 PM10/PM2.5(㎍/㎥). 키/네트워크 실패 시 None."""
    key = config.get_key("DATA_GO_KR_KEY")
    if not key:
        return None
    params = {"serviceKey": key, "returnType": "json", "numOfRows": 100,
              "pageNo": 1, "sidoName": "서울", "ver": "1.3"}
    try:
        r = requests.get(_AIR_URL, params=params, timeout=15)
        items = r.json()["response"]["body"]["items"]
    except Exception:
        return None
    match = [it for it in items if it.get("stationName") == station] or items
    if not match:
        return None
    it = match[0]

    def _f(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    return {"pm10": _f(it.get("pm10Value")), "pm25": _f(it.get("pm25Value")),
            "data_time": it.get("dataTime"), "station": it.get("stationName")}


def fetch_forecast(nx: int = SONGPA_NX, ny: int = SONGPA_NY, when: dt.datetime | None = None) -> dict | None:
    """단기예보에서 `when`(없으면 현재)에 가장 가까운 시각의 기온·습도·풍속."""
    key = config.get_key("DATA_GO_KR_KEY")
    if not key:
        return None
    when = when or dt.datetime.now(SEOUL)
    # 최근 발표 base 부터 역순으로 시도(오래된 base도 향후 몇 일치 예보 포함).
    for back in (0, 1):
        base_date = (when.date() - dt.timedelta(days=back)).strftime("%Y%m%d")
        for bt in _BASE_TIMES:
            params = {"serviceKey": key, "dataType": "JSON", "numOfRows": 800,
                      "pageNo": 1, "base_date": base_date, "base_time": bt, "nx": nx, "ny": ny}
            try:
                r = requests.get(_FCST_URL, params=params, timeout=15)
                items = r.json()["response"]["body"]["items"]["item"]
            except Exception:
                continue
            if items:
                return _nearest_forecast(items, when)
    return None


def _nearest_forecast(items: list[dict], when: dt.datetime) -> dict:
    """예보 item 목록에서 target 시각에 가장 가까운 (TMP/REH/WSD)."""
    by_time: dict[str, dict] = {}
    for it in items:
        stamp = it["fcstDate"] + it["fcstTime"]
        by_time.setdefault(stamp, {})[it["category"]] = it["fcstValue"]
    target = when.strftime("%Y%m%d%H%M")
    # HHMM 예보(0000,0100,...)와 target(분 포함) 비교 → 절대차 최소.
    best = min(by_time, key=lambda s: abs(int(s) - int(target)))
    vals = by_time[best]

    def _f(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    return {"air_temp_c": _f(vals.get("TMP")), "humidity_pct": _f(vals.get("REH")),
            "wind_ms": _f(vals.get("WSD")), "fcst_time": best,
            "pty": int(_f(vals.get("PTY")) or 0), "pop": _f(vals.get("POP")),
            "pcp_mm": _pcp_mm(vals.get("PCP")), "sky": int(_f(vals.get("SKY")) or 0) or None}


def _pcp_mm(v) -> float | None:
    """PCP 문자열('강수없음'/'1.0mm'/'1mm 미만'…)에서 mm 수치를 최대한 뽑는다."""
    if v is None or "없음" in str(v):
        return None
    import re
    m = re.search(r"[-+]?\d*\.?\d+", str(v))
    return float(m.group()) if m else None


def fetch_forecast_series(nx: int = SONGPA_NX, ny: int = SONGPA_NY,
                          when: dt.datetime | None = None, hours: int = 12) -> list[dict]:
    """`when`부터 시간별 예보(기온·습도·풍속) 시퀀스. 위험지수를 시간 단위로 낼 때 쓴다."""
    key = config.get_key("DATA_GO_KR_KEY")
    if not key:
        return []
    when = when or dt.datetime.now(SEOUL)
    for back in (0, 1):
        base_date = (when.date() - dt.timedelta(days=back)).strftime("%Y%m%d")
        for bt in _BASE_TIMES:
            params = {"serviceKey": key, "dataType": "JSON", "numOfRows": 1000,
                      "pageNo": 1, "base_date": base_date, "base_time": bt, "nx": nx, "ny": ny}
            try:
                items = requests.get(_FCST_URL, params=params, timeout=15
                                     ).json()["response"]["body"]["items"]["item"]
            except Exception:
                continue
            if not items:
                continue
            by_time: dict[str, dict] = {}
            for it in items:
                by_time.setdefault(it["fcstDate"] + it["fcstTime"], {})[it["category"]] = it["fcstValue"]
            target = when.strftime("%Y%m%d%H%M")

            def _f(v):
                try:
                    return float(v)
                except (TypeError, ValueError):
                    return None
            series = []
            for stamp in sorted(by_time):
                if int(stamp) < int(target):  # 과거 예보 제외(stamp/target 모두 YYYYMMDDHHMM)
                    continue
                v = by_time[stamp]
                series.append({"stamp": stamp, "air_temp_c": _f(v.get("TMP")),
                               "humidity_pct": _f(v.get("REH")), "wind_ms": _f(v.get("WSD")),
                               "pty": int(_f(v.get("PTY")) or 0), "pop": _f(v.get("POP")),
                               "pcp_mm": _pcp_mm(v.get("PCP"))})
                if len(series) >= hours:
                    break
            if series:
                return series
    return []


def hourly_risk_series(when: dt.datetime | None = None, hours: int = 12,
                       params: "RiskParams | None" = None) -> list[dict]:
    """시간별 위험지수 — 예보(시간별 기온·습도) + 현재 PM으로 매 시각 산출.

    반환: [{hour:"HH", score, level, dominant}] · 위험지수는 날짜가 아니라 **시간 단위**로
    갱신되어야 하므로 이 함수가 홈 화면의 시간대별 신호등/권장 시간대를 채운다.
    """
    from engine.risk import compute_risk, walk_advisory
    from engine.schemas import RiskParams
    params = params or RiskParams()
    when = when or dt.datetime.now(SEOUL)
    air = fetch_air_quality() or {}
    pm10 = air.get("pm10") or 0.0
    pm25 = air.get("pm25") or 0.0
    series = fetch_forecast_series(when=when, hours=hours)
    out = []
    for pt in series:
        if pt["air_temp_c"] is None:
            continue
        t = dt.datetime.strptime(pt["stamp"], "%Y%m%d%H%M").replace(tzinfo=SEOUL)
        env = EnvObservation(
            timestamp=t, lat=SONGPA_CENTER[0], lon=SONGPA_CENTER[1],
            air_temp_c=pt["air_temp_c"], humidity_pct=pt["humidity_pct"] or 50.0,
            wind_ms=pt["wind_ms"] or 1.0, uv_index=0.0, pm10=pm10, pm25=pm25,
            road_surface_temp_c=pt["air_temp_c"], season=_season(t.month),
            precip_type_code=pt.get("pty") or 0, precip_prob_pct=pt.get("pop"),
            precip_mm=pt.get("pcp_mm"))
        r = compute_risk(env, params, missing={"uv", "surface"})
        adv = walk_advisory(env, r)  # 강수+위험 합산 게이트
        out.append({"hour": pt["stamp"][8:10], "score": round(r.score),
                    "level": r.level.value, "dominant": r.dominant, "temp": pt["air_temp_c"],
                    "pty": pt.get("pty") or 0, "pop": pt.get("pop"),
                    "advisory": adv.status, "rain": adv.rain})
    return out


def build_env_at(lat: float, lon: float,
                 when: dt.datetime | None = None) -> tuple[EnvObservation, set[str]]:
    """임의 좌표의 실측 환경 → (EnvObservation, missing).

    실측: 기온·습도·풍속·강수(해당 격자 단기예보) + PM10/PM2.5(에어코리아, 도시 내
    거의 균일하므로 서울 대표 관측소값 사용 — 지점별 정밀화는 최근접 관측소로 확장 가능).
    결측: 자외선(uv, API 미승인) · 노면온도(surface, RWIS 없음) → missing 집합.
    """
    when = when or dt.datetime.now(SEOUL)
    nx, ny = latlon_to_grid(lat, lon)
    air = fetch_air_quality() or {}
    fcst = fetch_forecast(nx=nx, ny=ny, when=when) or {}
    missing: set[str] = set()

    air_temp = fcst.get("air_temp_c")
    if air_temp is None:
        air_temp = 24.0
        missing.add("heat")
    humidity = fcst.get("humidity_pct") or 50.0
    wind = fcst.get("wind_ms") or 1.0

    pm10 = air.get("pm10")
    pm25 = air.get("pm25")
    if pm10 is None and pm25 is None:
        pm10, pm25 = 0.0, 0.0
        missing.add("pm")
    else:
        pm10 = pm10 if pm10 is not None else 0.0
        pm25 = pm25 if pm25 is not None else 0.0

    # 미제공 소스 → 결측 처리(compute_risk가 중립화).
    missing.add("uv")       # data.go.kr 자외선 API 미승인(403)
    missing.add("surface")  # RWIS 실측 없음(노면온도 추정 모델은 데이터 후)

    env = EnvObservation(
        timestamp=when,
        lat=lat, lon=lon,
        air_temp_c=air_temp, humidity_pct=humidity, wind_ms=wind,
        uv_index=0.0,                    # missing → 중립
        pm10=pm10, pm25=pm25,
        road_surface_temp_c=air_temp,    # placeholder, missing → 중립
        season=_season(when.month),
        precip_type_code=fcst.get("pty") or 0,   # 강수형태(비 게이트)
        precip_prob_pct=fcst.get("pop"),
        precip_mm=fcst.get("pcp_mm"),
        sky_code=fcst.get("sky"),
    )
    return env, missing


def build_songpa_env(when: dt.datetime | None = None) -> tuple[EnvObservation, set[str]]:
    """송파구 중심 기준 실데이터 환경(build_env_at의 편의 래퍼)."""
    return build_env_at(SONGPA_CENTER[0], SONGPA_CENTER[1], when)


__all__ = ["fetch_air_quality", "fetch_forecast", "fetch_forecast_series",
           "hourly_risk_series", "build_env_at", "build_songpa_env", "latlon_to_grid",
           "SONGPA_NX", "SONGPA_NY", "SONGPA_CENTER"]
