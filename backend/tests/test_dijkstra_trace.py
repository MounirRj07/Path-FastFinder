"""Vérifie que la trace donne exactement les mêmes résultats que dijkstra.py."""

import json
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra as scipy_dijkstra

from app.routing.dijkstra import dijkstra_csr, reconstruct_path
from app.routing.dijkstra_trace import dijkstra_trace, timed_trace


def make_grid(width=30, height=30, seed=0):
    """Petit graphe en grille, orienté, au format CSR, avec les attributs de Graph."""
    rng = np.random.default_rng(seed)
    src, dst = [], []
    for y in range(height):
        for x in range(width):
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < width and 0 <= ny < height:
                    src.append(y * width + x)
                    dst.append(ny * width + nx)
    src, dst = np.array(src), np.array(dst)
    order = np.lexsort((dst, src))
    src, dst = src[order], dst[order]
    n = width * height
    offsets = np.zeros(n + 1, dtype=np.int64)
    np.add.at(offsets, src + 1, 1)
    offsets = np.cumsum(offsets)

    coords = np.array([[2.3 + (i % width) * 1e-3, 6.4 + (i // width) * 1e-3] for i in range(n)])
    g = SimpleNamespace(
        offsets=offsets, targets=dst.astype(np.int32), sources=src.astype(np.int32),
        lengths=rng.uniform(30, 150, len(dst)), node_coords=coords, n_nodes=n,
    )
    g.edge_name = lambda e: f"rue {e}"
    g.edge_geometry = lambda e: np.array([coords[g.sources[e]], coords[g.targets[e]]])
    return g


@pytest.fixture(scope="module")
def graph_and_factors():
    g = make_grid()
    rng = np.random.default_rng(1)
    factors = np.ones(len(g.targets))
    factors[rng.choice(len(factors), 40, replace=False)] = 3.0      # pénalités
    factors[rng.choice(len(factors), 20, replace=False)] = np.inf   # routes fermées
    return g, factors


def test_meme_resultat_que_dijkstra_et_scipy(graph_and_factors):
    g, factors = graph_and_factors
    costs = g.lengths * factors
    finite = np.isfinite(costs)
    matrix = csr_matrix((costs[finite], (g.sources[finite], g.targets[finite])),
                        shape=(g.n_nodes, g.n_nodes))
    rng = np.random.default_rng(2)

    for _ in range(100):
        s, t = (int(v) for v in rng.integers(0, g.n_nodes, 2))
        dist, prev_n, prev_e, explored = dijkstra_csr(g.offsets, g.targets, costs, s, t)
        trace = dijkstra_trace(g.offsets, g.targets, costs, s, t, max_nodes=g.n_nodes)
        reference = scipy_dijkstra(matrix, indices=s)[t]

        assert trace.found == bool(np.isfinite(dist[t]))
        if trace.found:
            assert trace.distances[t] == pytest.approx(dist[t])
            assert trace.distances[t] == pytest.approx(reference)
            assert len(trace.settled) == explored
            assert reconstruct_path(s, t, trace.previous_nodes, trace.previous_edges) == \
                reconstruct_path(s, t, prev_n, prev_e)
        else:
            assert np.isinf(reference)
        # Propriété de Dijkstra : les distances fixées ne diminuent jamais
        assert np.all(np.diff(trace.settled_dist) >= 0)


def test_json_valide_et_complet(graph_and_factors):
    g, factors = graph_and_factors
    payload = timed_trace(g, factors, 0, g.n_nodes - 1, max_nodes=2000)
    json.dumps(payload, allow_nan=False)          # échoue s'il reste un inf ou un NaN
    assert payload["stats"]["found"] and not payload["stats"]["truncated"]
    assert payload["path"]["nodes"][0] == 0 and payload["path"]["nodes"][-1] == g.n_nodes - 1
    statuses = {r["status"] for step in payload["steps"] for r in step["relax"]}
    assert statuses == {"kept", "improved", "closed"}
    # Toutes les arêtes citées dans les étapes sont décrites dans "edges"
    described = {e["id"] for e in payload["edges"]}
    assert all(r["edge"] in described for step in payload["steps"] for r in step["relax"])


def test_troncature(graph_and_factors):
    g, factors = graph_and_factors
    payload = timed_trace(g, factors, 0, g.n_nodes - 1, max_nodes=30)
    assert payload["stats"]["truncated"] and payload["path"] is None
    assert len(payload["steps"]) == 30


def test_depart_egal_arrivee(graph_and_factors):
    g, factors = graph_and_factors
    payload = timed_trace(g, factors, 5, 5)
    assert payload["path"]["edges"] == [] and payload["stats"]["nodes_explored"] == 1