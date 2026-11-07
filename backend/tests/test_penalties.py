import numpy as np
import pytest

from datetime import datetime, timezone

from app.routing.penalties import (
    build_admin_factors,
    apply_admin_penalties
)


def test_penalty_levels():

    penalties = [
        {"edge_id": 0, "level": "light"},
        {"edge_id": 1, "level": "medium"},
        {"edge_id": 2, "level": "high"},
        {"edge_id": 3, "level": "closed"}
    ]

    factors = build_admin_factors(4, penalties)

    expected = np.array([1.5, 3.0, 10.0, np.inf])

    assert np.array_equal(factors, expected)


def test_multiple_penalties_use_maximum():

    penalties = [
        {"edge_id": 0, "level": "light"},
        {"edge_id": 0, "level": "medium"},
        {"edge_id": 0, "level": "high"}
    ]

    factors = build_admin_factors(1, penalties)

    assert factors[0] == 10.0


def test_inactive_penalty_is_ignored():

    penalties = [
        {
            "edge_id": 0,
            "level": "high",
            "is_active": False
        }
    ]

    factors = build_admin_factors(1, penalties)

    assert factors[0] == 1.0


def test_time_bounded_penalties():

    now = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)

    penalties = [
        {
            "edge_id": 0,
            "level": "high",
            "starts_at": "2026-11-06T13:00:00Z"
        },
        {
            "edge_id": 1,
            "level": "medium",
            "ends_at": "2026-11-06T11:00:00Z"
        },
        {
            "edge_id": 2,
            "level": "light",
            "starts_at": "2026-11-06T11:00:00Z",
            "ends_at": "2026-11-06T13:00:00Z"
        }
    ]

    factors = build_admin_factors(3, penalties, now)

    assert factors[0] == 1.0
    assert factors[1] == 1.0
    assert factors[2] == 1.5


def test_apply_admin_penalties():

    base_costs = np.array([100, 200, 300, 400])

    admin_factors = np.array([1, 1.5, 3, np.inf])

    effective_costs = apply_admin_penalties(
        base_costs,
        admin_factors
    )

    expected = np.array([100, 300, 900, np.inf])

    assert np.array_equal(effective_costs, expected)


def test_original_costs_are_not_modified():

    base_costs = np.array([100, 200])

    original = base_costs.copy()

    admin_factors = np.array([3, 10])

    apply_admin_penalties(base_costs, admin_factors)

    assert np.array_equal(base_costs, original)


def test_invalid_edge_id():

    penalties = [
        {"edge_id": 5, "level": "high"}
    ]

    with pytest.raises(ValueError):
        build_admin_factors(3, penalties)


def test_invalid_penalty_level():

    penalties = [
        {"edge_id": 0, "level": "extreme"}
    ]

    with pytest.raises(ValueError):
        build_admin_factors(1, penalties)