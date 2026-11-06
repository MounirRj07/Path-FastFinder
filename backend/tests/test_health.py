from fastapi.testclient import TestClient


def test_health(graph_dir, monkeypatch):
    monkeypatch.setenv("GRAPH_PATH", str(graph_dir))
    from app.main import app

    with TestClient(app) as client:      # le "with" declenche le chargement du graphe
        r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["graph"]["n_edges"] == 9
