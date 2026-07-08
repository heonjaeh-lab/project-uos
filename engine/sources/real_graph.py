"""실데이터 라우팅 그래프 — 송파구 실 OSM 건물·가로수로 그늘을 계산해 주입.

`engine.routing.build_routing_graph`에 OSM 실데이터(Building/Tree)를 넘겨,
mock 클러스터가 아니라 송파구 전역 실제 건물 그림자로 shade_ratio를 채운다.
환경(위험지수) 입력은 실시간 API 키가 없는 동안 provisional 값으로 둔다
(키가 연결되면 env만 교체).
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from engine.routing import build_routing_graph
from engine.schemas import EnvObservation
from engine.sources import osm

SEOUL = ZoneInfo("Asia/Seoul")
# 송파구 대략 중심(태양 위치 기준점). 수 km 내 태양각 차이는 무시 가능.
SONGPA_CENTER = (37.5145, 127.1059)


def default_when() -> datetime:
    """여름 저녁 6시(tz-aware). 무더위를 피한 산책 시간대이자, 태양이 낮아
    그림자가 길어 그늘 효과가 뚜렷하게 나타나는 시각."""
    return datetime(2026, 7, 8, 18, 0, tzinfo=SEOUL)


def build_real_routing_graph(
    *,
    when: datetime | None = None,
    env: EnvObservation | None = None,
    use_real_env: bool = True,
    cost_params=None,
):
    """송파구 실 OSM 건물·가로수로 그늘을 계산해 주입한 라우팅 그래프.

    `use_real_env=True`(기본)면 기상·대기질 실데이터(build_songpa_env)로 환경을 채워
    엣지 위험도(M2)에 반영한다. 키가 없으면 자동으로 mock 폴백.

    Returns:
        (G, buildings, trees, env, missing) — 그래프·실데이터·사용 환경·결측 요소.
    """
    when = when or default_when()
    missing: set[str] = set()
    if env is None and use_real_env:
        from engine.sources.weather import build_songpa_env
        try:
            env, missing = build_songpa_env(when)
        except Exception:
            env, missing = None, set()  # 실패 시 mock 폴백
    buildings = osm.fetch_buildings()  # 캐시에서 로드
    trees = osm.fetch_trees()
    G = build_routing_graph(
        buildings=buildings,
        trees=trees,
        shade_ref=SONGPA_CENTER,
        when=when,
        env=env,
        cost_params=cost_params,
    )
    return G, buildings, trees, env, missing


__all__ = ["build_real_routing_graph", "default_when", "SONGPA_CENTER", "SEOUL"]
