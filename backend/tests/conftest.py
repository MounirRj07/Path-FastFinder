"""
Petit graphe artificiel, au format produit par osmnx, pour tester sans Internet.

    105
     |              (100-105 : route droite de ~2 km, double sens)
     |
    100 ── 101 ── 102 ──▶ 103     (102 -> 103 : sens unique, tracé courbe)
            │ ▲
            ▼ │                    (101 -> 104 : deux arêtes parallèles, on garde la plus courte)
            104 ↺                  (boucle 104 -> 104 : supprimée)
"""

import sys
from pathlib import Path

import networkx as nx
import pytest
from shapely.geometry import LineString

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "preprocessing"))
sys.path.insert(0, str(ROOT / "backend"))

import build_graph  # noqa: E402

LAT = 6.45
COORDS = {
    100: (2.350, LAT),
    101: (2.351, LAT),
    102: (2.352, LAT),
    103: (2.353, LAT),
    104: (2.351, LAT - 0.001),
    105: (2.350, LAT + 0.018),
}


def make_osmnx_like_graph() -> nx.MultiDiGraph:
    G = nx.MultiDiGraph(crs="epsg:4326")
    for osmid, (x, y) in COORDS.items():
        G.add_node(osmid, x=x, y=y)

    def two_way(u, v, **data):
        G.add_edge(u, v, **data)
        G.add_edge(v, u, **data)

    two_way(100, 101, length=110.0, osmid=1, name="Rue A", highway="residential")
    two_way(101, 102, length=110.0, osmid=1, name="Rue A", highway="residential", speed_kph=40.0)
    G.add_edge(102, 103, length=140.0, osmid=2, name="Rue B", highway="tertiary",
               geometry=LineString([(2.352, LAT), (2.3525, LAT + 0.0003), (2.353, LAT)]))
    G.add_edge(101, 104, length=150.0, osmid=3, name="Rue C", highway="service")
    G.add_edge(101, 104, length=120.0, osmid=[3, 4], name=["Rue C", "Rue D"], highway=["service"])
    G.add_edge(104, 101, length=120.0, osmid=3, name="Rue C", highway="service")
    G.add_edge(104, 104, length=30.0, osmid=6, highway="service")
    two_way(100, 105, length=2000.0, osmid=5, highway="primary")
    return G


@pytest.fixture
def osm_graph():
    return make_osmnx_like_graph()


@pytest.fixture
def arrays(osm_graph):
    return build_graph.to_arrays(osm_graph)


@pytest.fixture
def graph_dir(tmp_path, arrays):
    out = tmp_path / "graph"
    build_graph.save(arrays, out, place="test")
    return out


@pytest.fixture
def graph(graph_dir):
    from app.routing.graph import Graph
    return Graph.load(graph_dir)


@pytest.fixture
def node(graph):
    """Identifiant interne d'un nœud à partir de son id OSM."""
    index = {int(o): i for i, o in enumerate(graph.node_osmids)}
    return lambda osmid: index[osmid]
