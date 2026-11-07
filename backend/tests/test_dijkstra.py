import numpy as np
import networkx as nx

from app.routing.dijkstra import (
    dijkstra_csr,
    reconstruct_path
)


def test_dijkstra_simple_graph():

    offsets = np.array([0, 2, 3, 3, 3])
    targets = np.array([1, 2, 3])
    costs = np.array([4.0, 2.0, 3.0])

    distances, previous_nodes, previous_edges, explored = dijkstra_csr(
        offsets,
        targets,
        costs,
        0,
        3
    )

    path = reconstruct_path(
        0,
        3,
        previous_nodes,
        previous_edges
    )

    assert distances[3] == 7.0
    assert path == [0, 2]
    assert explored > 0


def test_source_equals_target():

    offsets = np.array([0, 1, 1])
    targets = np.array([1])
    costs = np.array([5.0])

    distances, previous_nodes, previous_edges, explored = dijkstra_csr(
        offsets,
        targets,
        costs,
        0,
        0
    )

    path = reconstruct_path(
        0,
        0,
        previous_nodes,
        previous_edges
    )

    assert distances[0] == 0.0
    assert path == []


def test_unreachable_destination():

    offsets = np.array([0, 1, 1, 1])
    targets = np.array([1])
    costs = np.array([5.0])

    distances, previous_nodes, previous_edges, explored = dijkstra_csr(
        offsets,
        targets,
        costs,
        0,
        2
    )

    path = reconstruct_path(
        0,
        2,
        previous_nodes,
        previous_edges
    )

    assert np.isinf(distances[2])
    assert path == []


def test_closed_edge():

    offsets = np.array([0, 1, 1])
    targets = np.array([1])
    costs = np.array([np.inf])

    distances, previous_nodes, previous_edges, explored = dijkstra_csr(
        offsets,
        targets,
        costs,
        0,
        1
    )

    assert np.isinf(distances[1])

def test_dijkstra_against_networkx():

    rng = np.random.default_rng(42)

    number_of_nodes = 60

    adjacency = [[] for _ in range(number_of_nodes)]

    graph = nx.DiGraph()

    graph.add_nodes_from(range(number_of_nodes))

    # Génération d'un graphe orienté aléatoire
    for source in range(number_of_nodes):

        for target in range(number_of_nodes):

            if source != target and rng.random() < 0.08:

                weight = float(rng.integers(1, 20))

                adjacency[source].append((target, weight))

                graph.add_edge(
                    source,
                    target,
                    weight=weight
                )

    # Conversion du graphe en format CSR
    offsets = [0]
    targets = []
    costs = []

    for neighbors in adjacency:

        for target, weight in neighbors:

            targets.append(target)
            costs.append(weight)

        offsets.append(len(targets))

    offsets = np.array(offsets, dtype=np.int64)
    targets = np.array(targets, dtype=np.int64)
    costs = np.array(costs, dtype=np.float64)

    # Comparaison sur 100 paires aléatoires
    for _ in range(100):

        source = int(rng.integers(0, number_of_nodes))
        target = int(rng.integers(0, number_of_nodes))

        distances, _, _, _ = dijkstra_csr(
            offsets,
            targets,
            costs,
            source,
            target
        )

        try:

            expected_distance = nx.shortest_path_length(
                graph,
                source,
                target,
                weight="weight"
            )

        except nx.NetworkXNoPath:

            expected_distance = np.inf

        assert np.isclose(
            distances[target],
            expected_distance
        ), (
            f"Erreur pour source={source}, destination={target} : "
            f"notre résultat={distances[target]}, "
            f"NetworkX={expected_distance}"
        )
