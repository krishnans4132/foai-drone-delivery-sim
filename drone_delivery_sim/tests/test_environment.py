"""tests.test_environment

Unit tests for sim/environment.py:
- Graph neighbor calculations (bounds, 4 cardinal directions)
- Obstacle exclusion
- Restricted cell handling across weather types (Clear, Windy, Rain, Storm)
- Dynamically blocked cell handling
- Per-cell movement costs
- Nearest charging station helper
- Config loading and fleet capacity validation
"""

import json
from pathlib import Path
import pytest
from sim.environment import GridEnvironment, CellType, PackageEntity


def get_config_path() -> Path:
    return Path(__file__).parent.parent / "config.json"


def test_neighbors_boundary_exclusion():
    """Verify corner and boundary cells only return in-bounds neighbors."""
    env = GridEnvironment(width=10, height=10)

    # Top-left corner (0, 0)
    nbrs_corner = env.neighbors((0, 0), weather="Clear")
    assert sorted(nbrs_corner) == sorted([(0, 1), (1, 0)])

    # Bottom-right corner (9, 9)
    nbrs_br = env.neighbors((9, 9), weather="Clear")
    assert sorted(nbrs_br) == sorted([(9, 8), (8, 9)])

    # Center cell (5, 5) has all 4 cardinal neighbors
    nbrs_center = env.neighbors((5, 5), weather="Clear")
    assert sorted(nbrs_center) == sorted([(5, 4), (5, 6), (4, 5), (6, 5)])


def test_obstacle_exclusion():
    """Verify obstacle cells are never included in neighbors."""
    obstacles = [(5, 6), (6, 5)]
    env = GridEnvironment(width=10, height=10, obstacles=obstacles)

    nbrs = env.neighbors((5, 5), weather="Clear")
    assert (5, 6) not in nbrs
    assert (6, 5) not in nbrs
    assert sorted(nbrs) == sorted([(5, 4), (4, 5)])

    # Obstacle itself is not traversable
    assert not env.is_traversable((5, 6), weather="Clear")


def test_restricted_cell_weather_dynamics():
    """Verify restricted cells are passable in Clear/Windy, but impassable in Rain/Storm."""
    restricted = [(5, 6)]
    env = GridEnvironment(width=10, height=10, restricted_zones=restricted)

    # In Clear weather, (5, 6) is included
    nbrs_clear = env.neighbors((5, 5), weather="Clear")
    assert (5, 6) in nbrs_clear
    assert env.is_traversable((5, 6), weather="Clear")

    # In Windy weather, (5, 6) is included
    nbrs_windy = env.neighbors((5, 5), weather="Windy")
    assert (5, 6) in nbrs_windy
    assert env.is_traversable((5, 6), weather="Windy")

    # In Rain weather, restricted cells become impassable
    nbrs_rain = env.neighbors((5, 5), weather="Rain")
    assert (5, 6) not in nbrs_rain
    assert not env.is_traversable((5, 6), weather="Rain")

    # In Storm weather, restricted cells remain impassable
    nbrs_storm = env.neighbors((5, 5), weather="Storm")
    assert (5, 6) not in nbrs_storm
    assert not env.is_traversable((5, 6), weather="Storm")


def test_dynamically_blocked_cells():
    """Verify dynamically passed blocked_cells (e.g., storm hazards) are excluded."""
    env = GridEnvironment(width=10, height=10)
    blocked = {(5, 6), (4, 5)}

    nbrs = env.neighbors((5, 5), weather="Clear", blocked_cells=blocked)
    assert (5, 6) not in nbrs
    assert (4, 5) not in nbrs
    assert sorted(nbrs) == sorted([(5, 4), (6, 5)])


def test_move_costs_and_penalties():
    """Verify base move cost, weather multiplier, and restricted zone surcharge."""
    restricted = [(5, 6)]
    env = GridEnvironment(width=10, height=10, restricted_zones=restricted)

    # Normal move in Clear: 1.0
    cost_clear = env.get_move_cost((5, 5), (6, 5), weather="Clear")
    assert cost_clear == 1.0

    # Normal move in Windy: 1.5
    cost_windy = env.get_move_cost((5, 5), (6, 5), weather="Windy")
    assert cost_windy == 1.5

    # Move into restricted zone in Clear: 1.0 + 1.0 surcharge = 2.0
    cost_restr_clear = env.get_move_cost((5, 5), (5, 6), weather="Clear")
    assert cost_restr_clear == 2.0

    # Move into restricted zone in Windy: 1.5 + 1.0 surcharge = 2.5
    cost_restr_windy = env.get_move_cost((5, 5), (5, 6), weather="Windy")
    assert cost_restr_windy == 2.5

    # Attempt to move into restricted zone in Rain raises ValueError (impassable)
    with pytest.raises(ValueError):
        env.get_move_cost((5, 5), (5, 6), weather="Rain")


def test_nearest_charging_station():
    """Verify nearest charging station returns closest station by Manhattan distance."""
    stations = [(0, 0), (9, 9), (0, 9)]
    env = GridEnvironment(width=10, height=10, charging_stations=stations)

    # Closest to (1, 1) is (0, 0) (dist 2 vs dist 16 vs dist 9)
    nearest = env.get_nearest_charging_station((1, 1))
    assert nearest == (0, 0)

    # Closest to (8, 8) is (9, 9) (dist 2)
    assert env.get_nearest_charging_station((8, 8)) == (9, 9)

    # Empty charging stations returns None
    empty_env = GridEnvironment(width=10, height=10)
    assert empty_env.get_nearest_charging_station((5, 5)) is None


def test_from_config_loading_and_entities():
    """Verify loading from config.json correctly instantiates entities."""
    env = GridEnvironment.from_config(get_config_path())
    assert env.width == 20
    assert env.height == 20
    assert len(env.obstacles) > 0
    assert len(env.restricted_zones) > 0
    assert len(env.charging_stations) > 0
    assert len(env.packages) > 0

    # Check package entity fields
    pkg = next(iter(env.packages.values()))
    assert isinstance(pkg, PackageEntity)
    assert pkg.status == "PENDING"
    assert len(pkg.pickup) == 2
    assert len(pkg.destination) == 2


def test_fleet_capacity_validation():
    """Verify capacity validation logic and auto-generation of start cells."""
    env = GridEnvironment.from_config(get_config_path())

    # Valid fleet count
    is_valid, msg = env.validate_drone_capacity(3)
    assert is_valid is True

    # Invalid fleet count (< 1)
    is_valid, msg = env.validate_drone_capacity(0)
    assert is_valid is False
    assert "at least 1" in msg

    # Auto-generation when requested drones exceed initial start_locations list
    large_fleet_count = len(env.start_locations) + 5
    starts = env.ensure_start_locations(large_fleet_count, auto_generate=True)
    assert len(starts) == large_fleet_count
    # All auto-generated slots must be valid, in-bounds, and non-obstacles
    for s in starts:
        assert env.is_within_bounds(s)
        assert s not in env.obstacles
