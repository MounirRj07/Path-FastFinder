"""
Tests de l'API : contrat HTTP, validation des entrées, protection admin.

Aucun appel réseau ni base de données : DATABASE_URL est retiré de
l'environnement et l'authentification admin est remplacée par un faux utilisateur.
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(graph_dir, monkeypatch):
    monkeypatch.setenv("GRAPH_PATH", str(graph_dir))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "test-key")
    from app.main import app

    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def admin_client(client):
    from app.main import app
    from app.auth import require_admin

    app.dependency_overrides[require_admin] = lambda: "11111111-1111-1111-1111-111111111111"
    yield client
    app.dependency_overrides.clear()


VALID_PENALTY = {
    "edge_ids": [0],
    "level": "high",
    "reason": "Travaux",
    "starts_at": "2026-11-14T00:00:00Z",
    "ends_at": "2026-11-20T00:00:00Z",
}


# ---------- /route ----------

def test_route_returns_routes(client, graph):
    lon1, lat1 = graph.node_coords[0]
    lon2, lat2 = graph.node_coords[-1]
    r = client.get("/route", params={
        "from_lat": lat1, "from_lon": lon1,
        "to_lat": lat2, "to_lon": lon2, "alternatives": 2,
    })
    assert r.status_code == 200
    body = r.json()
    assert 1 <= len(body["routes"]) <= 3
    first = body["routes"][0]
    assert first["rank"] == 1
    assert first["distance_m"] > 0
    assert len(first["geometry"]) >= 2


def test_route_missing_parameter(client):
    r = client.get("/route", params={"from_lat": 6.45})
    assert r.status_code == 422


def test_route_alternatives_out_of_range(client, graph):
    lon, lat = graph.node_coords[0]
    r = client.get("/route", params={
        "from_lat": lat, "from_lon": lon,
        "to_lat": lat, "to_lon": lon, "alternatives": 3,
    })
    assert r.status_code == 422


def test_route_out_of_zone(client):
    r = client.get("/route", params={
        "from_lat": 0, "from_lon": 0, "to_lat": 0, "to_lon": 0,
    })
    assert r.status_code == 422


# ---------- Protection admin ----------

def test_admin_requires_token(client):
    r = client.get("/admin/edges/nearest", params={"lat": 6.45, "lon": 2.4})
    assert r.status_code == 401


def test_admin_rejects_non_bearer_scheme(client):
    r = client.get(
        "/admin/edges/nearest",
        params={"lat": 6.45, "lon": 2.4},
        headers={"Authorization": "Basic abc"},
    )
    assert r.status_code == 401


def test_admin_nearest_edge(admin_client, graph):
    lon, lat = graph.node_coords[0]
    r = admin_client.get("/admin/edges/nearest", params={"lat": lat, "lon": lon})
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["edge_ids"], list) and body["edge_ids"]
    assert "geometry" in body


# ---------- Validation des pénalités (rejetées avant toute écriture) ----------

def test_penalty_rejects_unknown_level(admin_client):
    body = {**VALID_PENALTY, "level": "fatal"}
    assert admin_client.post("/admin/penalties", json=body).status_code == 422


def test_penalty_rejects_end_before_start(admin_client):
    body = {**VALID_PENALTY, "starts_at": "2026-11-20T00:00:00Z", "ends_at": "2026-11-14T00:00:00Z"}
    assert admin_client.post("/admin/penalties", json=body).status_code == 422


def test_penalty_rejects_naive_datetime(admin_client):
    body = {**VALID_PENALTY, "starts_at": "2026-11-14T00:00:00"}
    assert admin_client.post("/admin/penalties", json=body).status_code == 422


def test_penalty_rejects_empty_reason(admin_client):
    body = {**VALID_PENALTY, "reason": ""}
    assert admin_client.post("/admin/penalties", json=body).status_code == 422


def test_penalty_rejects_unknown_edge(admin_client, graph):
    body = {**VALID_PENALTY, "edge_ids": [graph.n_edges]}
    assert admin_client.post("/admin/penalties", json=body).status_code == 422