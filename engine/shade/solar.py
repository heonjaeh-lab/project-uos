"""태양 위치 및 그림자 벡터 계산 (M1 그늘 계산의 기하 기반).

순수 기하/천문 계산이며 ML·추정·난수가 없다. 시각(`when`)을 **인자로 받아**
같은 입력이면 항상 같은 결과를 내도록 결정론을 보장한다(현재시각 자동조회 금지).

- 태양 고도(elevation)·방위(azimuth)는 `astral`로 구한다.
- 방위 규약: 북=0°, 동=90°, 남=180°, 서=270° (태양이 있는 방향, 시계방향).
- 길이·이동은 **투영 CRS(m)** 에서 쓰라고 만든 값이다(위경도(도)에서 쓰면 무의미).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from astral import Observer
from astral.sun import azimuth, elevation


@dataclass(frozen=True)
class SunPosition:
    """태양 위치. 각도는 degree.

    - `elevation_deg`: 지평선 위 고도(°). <=0 이면 해가 진 상태(야간).
    - `azimuth_deg`: 방위(°, 북=0, 동=90, 남=180, 서=270) — 태양이 있는 방향.
    """

    elevation_deg: float
    azimuth_deg: float

    @property
    def is_daylight(self) -> bool:
        """해가 지평선 위에 있는지(고도 > 0)."""
        return self.elevation_deg > 0.0


def sun_position(lat: float, lon: float, when: datetime) -> SunPosition:
    """관측 지점·시각의 태양 위치를 계산한다(결정론).

    Args:
        lat: 위도(°, WGS84).
        lon: 경도(°, WGS84).
        when: 관측 시각. **timezone-aware** 여야 한다(예: Asia/Seoul). naive 는
            시간대 모호성으로 재현성을 해치므로 거부한다.

    Returns:
        `SunPosition(elevation_deg, azimuth_deg)`.

    Raises:
        ValueError: `when` 이 tz-naive 인 경우.
    """
    if when.tzinfo is None or when.tzinfo.utcoffset(when) is None:
        raise ValueError(
            "sun_position: 'when' 은 timezone-aware datetime 이어야 한다"
            "(결정론·재현성 보장). 예: datetime(..., tzinfo=ZoneInfo('Asia/Seoul'))."
        )
    obs = Observer(latitude=lat, longitude=lon)
    return SunPosition(
        elevation_deg=float(elevation(obs, when)),
        azimuth_deg=float(azimuth(obs, when)),
    )


def shadow_vector(
    elevation_deg: float, azimuth_deg: float, height_m: float
) -> tuple[float, float] | None:
    """높이 `height_m` 물체가 드리우는 그림자의 평면 이동 벡터(m)를 구한다.

    - 그림자 방향 = 태양 반대편: `(azimuth + 180) % 360`.
    - 그림자 길이: `L = height_m / tan(elevation)` (태양이 낮을수록 김).
    - 방위 θ(북기준 시계방향)를 평면 벡터로: `dx = L*sin(θ)`(동=+x),
      `dy = L*cos(θ)`(북=+y). **투영 CRS(m)** 좌표에서 그대로 더하면 된다.

    Args:
        elevation_deg: 태양 고도(°).
        azimuth_deg: 태양 방위(°, 북=0 시계방향).
        height_m: 물체 높이(m).

    Returns:
        `(dx, dy)` 미터 이동 벡터. 해가 졌거나(고도<=0) 높이가 0 이하면 `None`.
    """
    if elevation_deg <= 0.0 or height_m <= 0.0:
        return None
    length_m = height_m / math.tan(math.radians(elevation_deg))
    shadow_azimuth = (azimuth_deg + 180.0) % 360.0
    theta = math.radians(shadow_azimuth)
    dx = length_m * math.sin(theta)  # 동(+x)
    dy = length_m * math.cos(theta)  # 북(+y)
    return (dx, dy)


__all__ = ["SunPosition", "sun_position", "shadow_vector"]
