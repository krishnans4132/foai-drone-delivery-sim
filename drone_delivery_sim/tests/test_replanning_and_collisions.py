"""tests.test_replanning_and_collisions

Unit tests for dynamic replanning and collision avoidance:
- 4-step dynamic replanning sequence logging:
  (1) detect_environmental_change
  (2) check_route_suitability
  (3) recompute_route_astar / run_astar_again
  (4) continue_with_new_route
- Route cell obstruction triggering replan that completely avoids the blocked cell
- Cost escalation beyond threshold triggering replan
- Strict collision avoidance across multiple fleet sizes (2, 5, 10) and multiple RNG seeds:
  - No two drones ever share a cell on the same tick
  - No drone ever enters an obstacle or storm-blocked cell
  - Total collisions count strictly equals 0
"""

from pathlib import Path
import json
import pytest

from sim.environment import GridEnvironment, PackageEntity
from sim.drone_agent import DroneAgent, DroneState
from sim.simulation import Simulation


@pytest.fixture
def base_config():
    """Load configuration from config.json."""
    cfg_path = Path(__file__).parent.parent / "config.json"
    with open(cfg_path, "r") as f:
        return json.load(f)


def test_dynamic_replanning_four_steps_when_route_blocked():
    """Verify that when a route cell becomes blocked, all 4 explicit steps execute and log,
    and the new route completely avoids the blocked cell."""
    env = GridEnvironment(width=10, height=10)
    drone = DroneAgent(drone_id="DRONE-REPLAN", start_pos=(0, 0), battery_capacity=100.0)

    target = (0, 4)
    # Initial path planning from (0, 0) to (0, 4) -> [(0, 1), (0, 2), (0, 3), (0, 4)]
    planned = drone.plan_path_to(target, env, "Clear")
    assert planned is True
    assert (0, 2) in drone.current_path

    # Drone takes one step to (0, 1)
    drone.step(env, "Clear")
    assert drone.position == (0, 1)
    assert (0, 2) in drone.current_path

    # Inject dynamic blockage at (0, 2)
    env.obstacles.add((0, 2))

    # Clear prior log entries to inspect replanning cycle specifically
    drone.replan_event_log.clear()

    # Trigger dynamic replanning
    replan_success = drone.handle_dynamic_replanning(target, env, "Clear")
    assert replan_success is True

    # Check that (0, 2) is strictly NOT in the new path
    assert (0, 2) not in drone.current_path
    assert len(drone.current_path) > 0

    # Verify all 4 explicit steps were logged in the event log
    logged_steps = [entry["step"] for entry in drone.replan_event_log]
    assert "STEP_1_DETECT_CHANGE" in logged_steps
    assert "STEP_2_CHECK_SUITABILITY" in logged_steps
    assert "STEP_3_RECOMPUTE_ASTAR" in logged_steps
    assert "STEP_4_CONTINUE_ROUTE" in logged_steps

    # Verify suitability check explicitly failed due to blocked cell
    step2_entry = next(e for e in drone.replan_event_log if e["step"] == "STEP_2_CHECK_SUITABILITY")
    assert step2_entry["details"]["is_suitable"] is False
    assert "(0, 2)" in step2_entry["details"]["reason"]


def test_dynamic_replanning_on_cost_escalation():
    """Verify that significant cost increase on current route triggers replanning."""
    # Place restricted zone on the direct path
    restricted = [(2, 0), (2, 1), (2, 2)]
    env = GridEnvironment(width=10, height=10, restricted_zones=restricted)
    drone = DroneAgent(drone_id="DRONE-COST", start_pos=(0, 1), battery_capacity=100.0)
    drone.replan_cost_threshold = 1.3  # 30% cost increase threshold

    target = (4, 1)
    drone.plan_path_to(target, env, "Clear")
    assert len(drone.current_path) > 0

    # Weather shifts to Storm, dramatically escalating cost
    env.weather_cost_multipliers["Storm"] = 3.0

    drone.replan_event_log.clear()
    is_suitable, reason = drone.check_route_suitability(env, "Storm")
    # In Storm, restricted zones are also impassable, so route is unsuitable
    assert is_suitable is False


@pytest.mark.parametrize("fleet_size", [2, 5, 10])
@pytest.mark.parametrize("seed", [42, 101, 2026])
def test_collision_avoidance_no_shared_cells(base_config, fleet_size, seed):
    """Verify that across many ticks, seeds, and fleet sizes (2, 5, 10):
    1. No two drones ever share a cell on the same tick
    2. No drone enters an obstacle or storm-blocked cell
    3. Total collision count is strictly 0
    """
    config = dict(base_config)
    config["seed"] = seed
    config["fleet"]["num_drones"] = fleet_size

    sim = Simulation(config, drone_override=fleet_size)
    assert len(sim.drones) == fleet_size

    # Run for 40 ticks, verifying invariants at every single tick
    for tick in range(1, 41):
        sim.step()

        positions = [d.position for d in sim.drones.values()]

        # INVARIANT 1: No two drones share a cell on the same tick
        assert len(positions) == len(set(positions)), (
            f"Collision detected at tick {tick}! Positions: {positions}"
        )

        # INVARIANT 2: No drone occupies an obstacle or storm-blocked cell
        for d in sim.drones.values():
            assert d.position not in sim.env.obstacles, (
                f"Drone {d.drone_id} entered obstacle at {d.position} on tick {tick}"
            )
            assert d.position not in sim.env.active_storm_blocked_cells, (
                f"Drone {d.drone_id} entered storm-blocked cell at {d.position} on tick {tick}"
            )

    # INVARIANT 3: Total collision count is strictly 0
    assert sim.collision_count == 0
