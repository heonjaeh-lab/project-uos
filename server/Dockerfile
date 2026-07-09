# 조심해야댕 GPS 라우팅 — python:3.13-slim. shapely/pyproj/geopandas는 manylinux wheel로 설치되어
# 시스템 geos/proj 없이도 import 된다(대개). wheel 누락으로 빌드 실패 시 Task 7 폴백 참고.
FROM python:3.13-slim

WORKDIR /app

COPY requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt

COPY engine ./engine
COPY server ./server
COPY scripts ./scripts   # engine.routing.graph_build 가 scripts.fetch_songpa_graph 를 import(모듈 레벨)

ENV PYTHONUNBUFFERED=1 PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn server.app:app --host 0.0.0.0 --port ${PORT}"]
