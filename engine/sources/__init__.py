"""실데이터 소스 어댑터.

각 어댑터는 외부 API/OSM에서 데이터를 받아 engine 스키마(M0) 또는 M1 입력
(Building/Tree)으로 매핑한다. 키가 필요한 소스는 `config.get_key`로 .env에서
키를 읽고, 키가 없으면 호출부가 mock로 폴백한다.

- osm: OSM 무료 데이터(건물 높이·POI·가로수) — 키 불필요
- (예정) kma/airkorea/seoul/vworld: 키 필요 소스
"""
