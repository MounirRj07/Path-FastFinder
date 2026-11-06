import json

import numpy as np
import pytest

from app.routing.graph import Graph, GraphFormatError


# ---------------------------------------------------------------- build_graph

def test_self_loop_removed_and_parallel_edges_merged(arrays):
    # 11 arêtes osmnx - 1 boucle - 1 arête parallèle = 9
    assert len(arrays["targets"]) == 9


def test_csr_offsets_are_consistent(arrays):
    offsets, sources = arrays["offsets"], arrays["sources"]
    assert offsets[0] == 0 and offsets[-1] == len(sources)
    for u in range(len(offsets) - 1):
        assert np.all(sources[offsets[u]:offsets[u + 1]] == u)


def test_edges_sorted_by_source_then_target(arrays):
    pairs = list(zip(arrays["sources"].tolist(), arrays["targets"].tolist()))
    assert pairs == sorted(pairs)


def test_default_speed_used_when_missing(graph, node):
    e = graph.find_edge(node(100), node(101))
    assert graph.speeds[e] == 25          # residential, pas de speed_kph
    e = graph.find_edge(node(101), node(102))
    assert graph.speeds[e] == 40          # speed_kph fourni par OSM


def test_list_attributes_are_flattened(graph, node):
    e = graph.find_edge(node(101), node(104))
    assert graph.lengths[e] == 120.0      # la plus courte des deux arêtes parallèles
    assert graph.way_ids[e] == 3
    assert graph.edge_name(e) == "Rue C / Rue D"
    assert graph.edge_highway(e) == "service"


# ---------------------------------------------------------------- Graph

def test_one_way_has_no_reverse(graph, node):
    e = graph.find_edge(node(102), node(103))
    assert e is not None
    assert graph.find_edge(node(103), node(102)) is None
    assert graph.reverse_edge(e) is None


def test_two_way_reverse(graph, node):
    e = graph.find_edge(node(100), node(101))
    r = graph.reverse_edge(e)
    assert graph.sources[r] == node(101) and graph.targets[r] == node(100)


def test_curved_geometry_kept_and_oriented(graph, node):
    e = graph.find_edge(node(102), node(103))
    geom = graph.edge_geometry(e)
    assert len(geom) == 3
    assert tuple(geom[0]) == (2.352, 6.45) and tuple(geom[-1]) == (2.353, 6.45)


def test_path_geometry_has_no_duplicate_joints(graph, node):
    path = [graph.find_edge(node(100), node(101)),
            graph.find_edge(node(101), node(102)),
            graph.find_edge(node(102), node(103))]
    coords = graph.path_geometry(path)
    assert len(coords) == 2 + 1 + 2       # 2 points + 1 nouveau + 2 nouveaux
    distance, duration = graph.path_stats(path)
    assert distance == pytest.approx(360.0)
    assert duration > 0


def test_edges_of_way_includes_both_directions(graph):
    edges = graph.edges_of_way(1)         # Rue A : 100-101-102, double sens
    assert len(edges) == 4
    assert len(graph.edges_of_way(999)) == 0


def test_meta(graph):
    assert graph.meta["n_nodes"] == 6
    assert graph.meta["n_edges"] == 9


# ---------------------------------------------------------------- validation

def test_missing_directory():
    with pytest.raises(GraphFormatError):
        Graph.load("/chemin/inexistant")


def test_missing_file(graph_dir):
    (graph_dir / "lengths.npy").unlink()
    with pytest.raises(GraphFormatError):
        Graph.load(graph_dir)


def test_corrupted_offsets(graph_dir):
    offsets = np.load(graph_dir / "offsets.npy")
    offsets[-1] += 1
    np.save(graph_dir / "offsets.npy", offsets)
    with pytest.raises(GraphFormatError, match="offsets"):
        Graph.load(graph_dir)


def test_wrong_format_version(graph_dir):
    meta = json.loads((graph_dir / "meta.json").read_text())
    meta["format_version"] = 99
    (graph_dir / "meta.json").write_text(json.dumps(meta))
    with pytest.raises(GraphFormatError, match="Version"):
        Graph.load(graph_dir)
