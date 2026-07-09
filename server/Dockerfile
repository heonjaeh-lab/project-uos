# 조심해야댕 GPS 라우팅 — python:3.13-slim. shapely/pyproj/geopandas는 manylinux wheel로 설치되어
# 시스템 geos/proj 없이도 import 된다(대개). wheel 누락으로 빌드 실패 시 Task 7 폴백 참고.
FROM python:3.13-slim

WORKDIR /app

COPY requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt

COPY engine ./engine
COPY server ./server
# engine.routing.graph_build 가 scripts.fetch_songpa_graph 를 import(모듈 레벨) → scripts/ 필요
COPY scripts ./scripts

# 비루트 강등(최소 권한). data/cache(그래프·건물 타일)를 런타임에 /app 아래로 쓰므로 소유권 부여.
RUN useradd -m -u 10001 app && mkdir -p /app/data && chown -R app:app /app
USER app

ENV PYTHONUNBUFFERED=1 PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn server.app:app --host 0.0.0.0 --port ${PORT}"]
