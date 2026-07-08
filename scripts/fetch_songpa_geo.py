"""송파구 건물·POI·가로수를 OSM에서 받아 data/cache/ 에 캐시(1회).

실행: .venv/bin/python scripts/fetch_songpa_geo.py
"""
from engine.sources import osm

if __name__ == "__main__":
    b = osm.fetch_buildings(force=True)
    print(f"buildings: {len(b)} (예: height={b[0].height_m}m, ring_pts={len(b[0].footprint)})")
    t = osm.fetch_trees(force=True)
    print(f"trees: {len(t)}")
    p = osm.fetch_pois(force=True)
    from collections import Counter
    c = Counter(x.poi_type.value for x in p)
    print(f"pois: {len(p)} {dict(c)}")
    print("CACHED at data/cache/{songpa_buildings,songpa_trees,songpa_pois}.json")
