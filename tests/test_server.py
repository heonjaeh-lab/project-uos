"""FastAPI GPS 라우팅 서버 — 핸들러 계약(엔진은 monkeypatch, 네트워크 없음)."""
from __future__ import annotations

from fastapi.testclient import TestClient

import server.app as srv

client = TestClient(srv.app)

_FAKE = {
    "bbox": [127.0, 37.5, 127.01, 37.51], "gps": {"lon": 127.0, "lat": 37.5},
    "origin": [127.0, 37.5], "dest": [127.01, 37.51],
    "routes": [{"label": "동네 순환", "shade": 0.5, "distance_m": 1800,
                "est_time_min": 24.0, "max_risk": "green", "segs": [], "pois": []}],
    "hourly": [], "meta": {"advisory": "go"},
}


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_route_ok(monkeypatch):
    monkeypatch.setattr(srv, "gps_map_payload", lambda *a, **k: _FAKE)
    r = client.get("/api/route?lat=37.5&lon=127.0")
    assert r.status_code == 200
    assert r.json()["routes"][0]["label"] == "동네 순환"


def test_route_passes_dest(monkeypatch):
    seen = {}
    def spy(lat, lon, dest=None, **k):
        seen["dest"] = dest
        return _FAKE
    monkeypatch.setattr(srv, "gps_map_payload", spy)
    client.get("/api/route?lat=37.5&lon=127.0&dest_lat=37.51&dest_lon=127.02")
    assert seen["dest"] == (37.51, 127.02)


def test_route_no_route_404(monkeypatch):
    monkeypatch.setattr(srv, "gps_map_payload", lambda *a, **k: {"routes": []})
    assert client.get("/api/route?lat=37.5&lon=127.0").status_code == 404


def test_route_engine_error_502(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("osm down")
    monkeypatch.setattr(srv, "gps_map_payload", boom)
    assert client.get("/api/route?lat=37.5&lon=127.0").status_code == 502


def test_route_bad_param_422():
    assert client.get("/api/route?lat=999&lon=127").status_code == 422
