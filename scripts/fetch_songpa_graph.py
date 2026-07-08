"""송파구 보행 네트워크를 OSM에서 1회 받아 GraphML로 캐시한다.

엔진 import 시 네트워크를 타지 않도록 다운로드를 이 스크립트로 분리한다.
실행: .venv/bin/python scripts/fetch_songpa_graph.py
"""
import os

import osmnx as ox

CACHE_PATH = "data/cache/songpa_walk.graphml"
PLACE = "Songpa-gu, Seoul, South Korea"


def build_songpa_graph(path: str = CACHE_PATH):
    """캐시가 있으면 로드, 없으면 OSM에서 받아 저장 후 반환."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        return ox.load_graphml(path)
    ox.settings.use_cache = True
    ox.settings.cache_folder = "data/cache"
    graph = ox.graph_from_place(PLACE, network_type="walk")
    ox.save_graphml(graph, path)
    return graph


if __name__ == "__main__":
    g = build_songpa_graph()
    print(f"nodes={g.number_of_nodes()} edges={g.number_of_edges()} cached_at={CACHE_PATH}")
