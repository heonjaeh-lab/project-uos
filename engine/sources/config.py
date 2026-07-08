"""API 키·설정 로더. 프로젝트 루트의 `.env`(gitignore됨)에서 값을 읽는다.

python-dotenv 의존 없이 단순 파서로 처리한다. 우선순위: 실제 환경변수 > .env 파일.
키가 없으면 None을 돌려주고, 호출부가 mock 폴백을 결정한다(엔진은 절대 죽지 않는다).
"""

from __future__ import annotations

import os
from functools import lru_cache

_ENV_PATH = ".env"


@lru_cache(maxsize=1)
def _dotenv() -> dict[str, str]:
    """`.env` 파일을 {KEY: VALUE} 로 파싱(주석·빈 줄 무시)."""
    values: dict[str, str] = {}
    if not os.path.exists(_ENV_PATH):
        return values
    with open(_ENV_PATH, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            values[key.strip()] = val.strip().strip('"').strip("'")
    return values


def get_key(name: str) -> str | None:
    """API 키를 얻는다. 실제 환경변수 우선, 없으면 .env, 그래도 없으면 None."""
    val = os.environ.get(name)
    if val:
        return val
    val = _dotenv().get(name)
    return val or None


def has_key(name: str) -> bool:
    return bool(get_key(name))
