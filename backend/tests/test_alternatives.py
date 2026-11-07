
import numpy as np
import pytest

from backend.app.routing.alternatives import (
    Route,
    compute_routes,
    _is_valid_alternative
)


def create_test_graph():

    offsets = np.array([0, 3, 5, 6, 7, 7])

    targets = np.array([
        1, 2, 3,
        4, 4,
        4,
        4
    ])

    lengths = np.array([
        1000, 1200, 1500,
        1000, 1200,
        1500,
        1800
    ], dtype=np.float64)

    speeds = np.full(7, 50.0)

    return offsets, targets, lengths, speeds


def test_compute_three_routes():

    offsets, targets, lengths, speeds = create_test_graph()

    routes = compute_routes(
        offsets,
        targets,
        lengths,
        speeds,
        source=0,
        target=4,
        k=3
    )

    assert len(routes) == 3

    assert routes[0].distance_m == 2000

    assert len(set(tuple(route.edges) for route in routes)) == 3


def test_compute_only_one_route():

    offsets, targets, lengths, speeds = create_test_graph()

    routes = compute_routes(
        offsets,
        targets,
        lengths,
        speeds,
        source=0,
        target=4,
        k=1
    )

    assert len(routes) == 1


def test_administrative_penalties_are_preserved():

    offsets, targets, lengths, speeds = create_test_graph()

    admin_factors = np.array([
        3, 1, 1, 1, 1, 1, 1
    ], dtype=np.float64)

    original_factors = admin_factors.copy()

    compute_routes(
        offsets,
        targets,
        lengths,
        speeds,
        source=0,
        target=4,
        admin_factors=admin_factors,
        k=3
    )

    assert np.array_equal(admin_factors, original_factors)


def test_invalid_k():

    offsets, targets, lengths, speeds = create_test_graph()

    with pytest.raises(ValueError):

        compute_routes(
            offsets,
            targets,
            lengths,
            speeds,
            source=0,
            target=4,
            k=4
        )


def test_unreachable_destination():

    offsets = np.array([0, 1, 1, 1])
    targets = np.array([1])

    lengths = np.array([1000.0])
    speeds = np.array([50.0])

    routes = compute_routes(
        offsets,
        targets,
        lengths,
        speeds,
        source=0,
        target=2,
        k=3
    )

    assert routes == []


def test_reject_alternative_with_more_than_70_percent_overlap():

    lengths = np.array([40, 30, 20, 10], dtype=np.float64)

    candidate = Route(
        nodes=[0, 1, 2, 3, 4],
        edges=[0, 1, 2, 3],
        distance_m=100,
        duration_s=10,
        penalized_edges=[]
    )

    selected_route = Route(
        nodes=[0, 1, 2, 4],
        edges=[0, 1, 2],
        distance_m=90,
        duration_s=9,
        penalized_edges=[]
    )

    result = _is_valid_alternative(
        candidate,
        [selected_route],
        primary_distance=100,
        lengths=lengths
    )

    assert result is False


def test_accept_alternative_with_exactly_70_percent_overlap():

    lengths = np.array([40, 30, 20, 10], dtype=np.float64)

    candidate = Route(
        nodes=[0, 1, 2, 3, 4],
        edges=[0, 1, 2, 3],
        distance_m=100,
        duration_s=10,
        penalized_edges=[]
    )

    selected_route = Route(
        nodes=[0, 1, 4],
        edges=[0, 1],
        distance_m=70,
        duration_s=7,
        penalized_edges=[]
    )

    result = _is_valid_alternative(
        candidate,
        [selected_route],
        primary_distance=100,
        lengths=lengths
    )

    assert result is True


def test_reject_alternative_exceeding_1_5_distance_ratio():

    lengths = np.array([151, 100], dtype=np.float64)

    candidate = Route(
        nodes=[0, 1],
        edges=[0],
        distance_m=151,
        duration_s=10,
        penalized_edges=[]
    )

    selected_route = Route(
        nodes=[0, 2],
        edges=[1],
        distance_m=100,
        duration_s=8,
        penalized_edges=[]
    )

    result = _is_valid_alternative(
        candidate,
        [selected_route],
        primary_distance=100,
        lengths=lengths
    )

    assert result is False


def test_accept_alternative_at_exactly_1_5_distance_ratio():

    lengths = np.array([150, 100], dtype=np.float64)

    candidate = Route(
        nodes=[0, 1],
        edges=[0],
        distance_m=150,
        duration_s=12,
        penalized_edges=[]
    )

    selected_route = Route(
        nodes=[0, 2],
        edges=[1],
        distance_m=100,
        duration_s=8,
        penalized_edges=[]
    )

    result = _is_valid_alternative(
        candidate,
        [selected_route],
        primary_distance=100,
        lengths=lengths
    )

    assert result is True
