"""기상청 격자 변환(latlon_to_grid) 검증 — 임의 좌표 예보 조회용(순수 계산, 네트워크 불필요)."""

from engine.sources.weather import latlon_to_grid


def test_known_grid_points():
    # 기상청 단기예보 격자의 알려진 좌표들과 일치해야 한다.
    assert latlon_to_grid(37.5145, 127.1059) == (62, 126)   # 송파구 중심
    assert latlon_to_grid(37.5665, 126.9780) == (60, 127)   # 서울시청


def test_grid_is_deterministic():
    assert latlon_to_grid(37.4979, 127.0276) == latlon_to_grid(37.4979, 127.0276)
