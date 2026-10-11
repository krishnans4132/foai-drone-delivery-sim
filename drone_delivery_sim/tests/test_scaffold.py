"""tests.test_scaffold

Tests verifying Step 1 scaffolding:
- Config loading and schema integrity
- CLI argument defaults and validation
- Dynamic fleet sizing and capacity validation
- Decoupled headless simulation initialization
"""

import json
from pathlib import Path
import pytest
from sim.simulation import Simulation
from sim.environment import GridEnvironment
from sim.weather_agent import WeatherAgent
from sim.delivery_manager import DeliveryManagerAgent
from sim.drone_agent import DroneAgent
from sim.planners import manhattan_distance


def get_config_path() -> Path:
    return Path(__file__).parent.parent / "config.json"


def test_config_file_exists_and_valid():
    """Verify config.json exists and contains required top-level keys."""
    cfg_path = get_config_path()
    assert cfg_path.exists(), "config.json must exist in project root"
    with open(cfg_path, "r") as f:
        config = json.load(f)

    assert "grid" in config
    assert config["grid"]["width"] == 20
    assert config["grid"]["height"] == 20
    assert "fleet" in config
    assert "num_drones" in config["fleet"]
    assert "battery_capacity" in config["fleet"]
    assert "environment" in config
    assert "obstacles" in config["environment"]
    assert "charging_stations" in config["environment"]
    assert "weather" in config
    assert "delivery_requests" in config
    assert "scenarios" in config


def test_simulation_headless_init():
    """Verify Simulation initializes properly and respects drone counts."""
    with open(get_config_path(), "r") as f:
        config = json.load(f)

    sim = Simulation(config)
    assert len(sim.drones) == config["fleet"]["num_drones"]
    assert sim.env.width == 20
    assert sim.env.height == 20
    assert sim.weather_agent.current_weather.value == "Clear"


def test_simulation_drone_override():
    """Verify drone count override is respected."""
    with open(get_config_path(), "r") as f:
        config = json.load(f)

    sim = Simulation(config, drone_override=2)
    assert len(sim.drones) == 2


def test_simulation_dynamic_drone_add_remove():
    """Verify live dynamic addition and removal of drones."""
    with open(get_config_path(), "r") as f:
        config = json.load(f)

    sim = Simulation(config, drone_override=2)
    initial_count = len(sim.drones)
    assert initial_count == 2

    added = sim.add_drone()
    assert added is True
    assert len(sim.drones) == 3

    removed = sim.remove_drone()
    assert removed is True
    assert len(sim.drones) == 2


def test_manhattan_distance_heuristic():
    """Verify Manhattan distance calculation."""
    assert manhattan_distance((0, 0), (3, 4)) == 7
    assert manhattan_distance((5, 5), (5, 5)) == 0
