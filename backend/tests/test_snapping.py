import pytest

from app.routing.snapping import OutOfZoneError, Snapper

LAT = 6.45


@pytest.fixture
def snapper(graph):
    return Snapper(graph)


def test_nearest_node(snapper, node):
    n, dist = snapper.nearest_node(LAT + 0.0001, 2.3511)   # ~15 m de 101
    assert n == node(101)
    assert dist < 20


def test_out_of_zone(snapper):
    with pytest.raises(OutOfZoneError):
        snapper.nearest_node(LAT + 0.1, 2.35)               # ~11 km au nord
    with pytest.raises(OutOfZoneError):
        snapper.nearest_edge(LAT + 0.1, 2.35)


def test_nearest_edge_on_curved_road(snapper, graph, node):
    # Clic sur le sommet de la courbe de la rue B (sens unique 102 -> 103)
    e, dist = snapper.nearest_edge(LAT + 0.00028, 2.3525)
    assert (graph.sources[e], graph.targets[e]) == (node(102), node(103))
    assert dist < 5


def test_nearest_edge_near_end_of_long_straight_road(snapper, graph, node):
    # Route droite 100-105 de 2 km : clic près de 105, loin du milieu de la route
    e, dist = snapper.nearest_edge(LAT + 0.0175, 2.35003)
    assert {int(graph.sources[e]), int(graph.targets[e])} == {node(100), node(105)}
    assert dist < 5


def test_select_road_two_way_returns_both_directions(snapper, graph, node):
    edges = snapper.select_road(LAT + 0.00002, 2.3505)      # sur 100-101
    pairs = {(int(graph.sources[e]), int(graph.targets[e])) for e in edges}
    assert pairs == {(node(100), node(101)), (node(101), node(100))}


def test_select_road_one_way_returns_one_edge(snapper):
    assert len(snapper.select_road(LAT + 0.00028, 2.3525)) == 1


def test_select_whole_way(snapper):
    edges = snapper.select_road(LAT + 0.00002, 2.3505, whole_way=True)
    assert len(edges) == 4                                  # toute la rue A, deux sens
