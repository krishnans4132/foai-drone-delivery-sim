"""tests.test_drone_agent

Unit tests for sim/drone_agent.py:
- Battery drain per move (Clear, Windy, Rain, Storm) and hover
- Low-battery charging detour behavior (divert to charger, recharge, resume mission)
- Full end-to-end pickup-and-deliver cycle on a small map
- Swappable planner support (A*, BFS, UCS, DFS)
- create_drone_fleet factory function (non-hardcoded fleet sizing)
"""

from pathlib import Path
import json
import pytest

from sim.environment import GridEnvironment, PackageEntity
from sim.drone_agent import DroneAgent, DroneState, DroneAction, create_drone_fleet
from sim.planners import AStarPlanner, BFSPlanner, UCSPlanner, DFSPlanner


@pytest.fixture
def small_env():
    """Create a 6x6 test grid with a charging station at (0, 0)."""
    return GridEnvironment(
        width=6,
        height=6,
        obstacles=[(2, 2)],
        charging_stations=[(0, 0)],
        start_locations=[(0, 0), (0, 1), (1, 0)],
    )


def test_battery_drain_move_across_weather(small_env):
    """Verify battery drain per movement reflects weather cost multipliers."""
    drone = DroneAgent(
        drone_id="DRONE-01",
        start_pos=(0, 1),
        battery_capacity=100.0,
        move_cost=1.0,
        hover_cost=0.5,
    )

    # 1. Move under Clear weather (cost: 1.0)
    drone.current_path = [(0, 2)]
    drone.step(small_env, "Clear")
    assert drone.position == (0, 2)
    assert drone.battery == pytest.approx(99.0)

    # 2. Move under Windy weather (cost: 1.5)
    drone.current_path = [(0, 3)]
    drone.step(small_env, "Windy")
    assert drone.position == (0, 3)
    assert drone.battery == pytest.approx(99.0 - 1.5)

    # 3. Move under Rain weather (cost: 2.0)
    drone.current_path = [(0, 4)]
    drone.step(small_env, "Rain")
    assert drone.position == (0, 4)
    assert drone.battery == pytest.approx(99.0 - 1.5 - 2.0)

    # 4. Move under Storm weather (cost: 3.0)
    drone.current_path = [(0, 5)]
    drone.step(small_env, "Storm")
    assert drone.position == (0, 5)
    assert drone.battery == pytest.approx(99.0 - 1.5 - 2.0 - 3.0)


def test_battery_drain_hover(small_env):
    """Verify hover action expends hover energy scaled by weather multiplier."""
    drone = DroneAgent(
        drone_id="DRONE-01",
        start_pos=(0, 0),
        battery_capacity=100.0,
        hover_cost=0.5,
    )
    drone.state = DroneState.HOVERING

    # Hover in Clear: 0.5 * 1.0 = 0.5
    action = drone.step(small_env, "Clear")
    assert action == DroneAction.HOVER
    assert drone.battery == pytest.approx(99.5)

    # Hover in Windy: 0.5 * 1.5 = 0.75
    drone.step(small_env, "Windy")
    assert drone.battery == pytest.approx(99.5 - 0.75)


def test_low_battery_charging_detour(small_env):
    """Verify drone diverts to charger when battery is low, recharges, and resumes."""
    # Place drone at (3, 3) with low battery (15.0 <= threshold 25.0)
    drone = DroneAgent(
        drone_id="DRONE-01",
        start_pos=(3, 3),
        battery_capacity=100.0,
        low_battery_threshold=25.0,
        charge_rate=30.0,
    )
    drone.battery = 15.0  # Explicitly low battery
    task = PackageEntity(
        id="PKG-DETOUR",
        pickup=(4, 4),
        destination=(5, 5),
        deadline_ticks=50,
    )
    drone.assign_task(task)

    # First step: Drone perceives low battery, triggers GOING_TO_CHARGE to (0, 0)
    drone.step(small_env, "Clear")
    assert drone.state == DroneState.GOING_TO_CHARGE
    assert drone.active_charger_target == (0, 0)
    assert drone.resume_state == DroneState.GOING_TO_PICKUP

    # Step drone until it reaches the charging station (0, 0)
    ticks = 0
    while drone.position != (0, 0) and ticks < 20:
        drone.step(small_env, "Clear")
        ticks += 1

    assert drone.position == (0, 0)
    # Next step docks and enters CHARGING state
    drone.step(small_env, "Clear")
    assert drone.state == DroneState.CHARGING

    # Step through charging until fully charged
    charge_ticks = 0
    while drone.state == DroneState.CHARGING and charge_ticks < 10:
        drone.step(small_env, "Clear")
        charge_ticks += 1

    # Drone must have resumed GOING_TO_PICKUP with restored battery
    assert drone.battery >= 90.0
    assert drone.state == DroneState.GOING_TO_PICKUP


def test_full_pickup_and_deliver_small_map(small_env):
    """Verify end-to-end execution: GOING_TO_PICKUP -> PICKUP -> DELIVERING -> DELIVER -> DONE."""
    drone = DroneAgent(
        drone_id="DRONE-01",
        start_pos=(0, 0),
        battery_capacity=100.0,
    )
    task = PackageEntity(
        id="PKG-FULL",
        pickup=(1, 3),
        destination=(4, 4),
        deadline_ticks=50,
    )
    drone.assign_task(task)

    assert drone.state == DroneState.GOING_TO_PICKUP
    assert drone.has_package is False

    visited_positions = [drone.position]
    max_steps = 30
    steps = 0

    while drone.state != DroneState.DONE and steps < max_steps:
        action = drone.step(small_env, "Clear")
        visited_positions.append(drone.position)
        steps += 1

    # Assert successful delivery completion
    assert drone.state == DroneState.DONE
    assert drone.position == (4, 4)
    assert drone.has_package is False
    assert task.status == "DELIVERED"
    assert len(drone.completed_tasks) == 1
    assert (1, 3) in visited_positions  # Must have visited pickup
    assert drone.battery < 100.0        # Battery consumed during flight
    assert drone.total_distance_moved > 0


def test_swappable_planners(small_env):
    """Verify drone operates correctly with different path planners."""
    planners = [AStarPlanner(), BFSPlanner(), UCSPlanner(), DFSPlanner()]

    for planner in planners:
        drone = DroneAgent(
            drone_id="DRONE-TEST",
            start_pos=(0, 0),
            battery_capacity=100.0,
            planner=planner,
        )
        task = PackageEntity(
            id=f"PKG-{planner.name}",
            pickup=(1, 2),
            destination=(3, 3),
            deadline_ticks=40,
        )
        drone.assign_task(task)

        # Run 10 ticks and ensure no exceptions
        for _ in range(15):
            if drone.state == DroneState.DONE:
                break
            drone.step(small_env, "Clear")

        assert drone.state in (DroneState.GOING_TO_PICKUP, DroneState.DELIVERING, DroneState.DONE)


def test_create_drone_fleet_factory(small_env):
    """Verify create_drone_fleet factory builds non-hardcoded fleets with capacity allocation."""
    config = {
        "fleet": {
            "battery_capacity": 100.0,
            "low_battery_threshold": 20.0,
            "charge_rate_per_tick": 20.0,
            "move_energy_cost": 1.0,
            "hover_energy_cost": 0.5,
        }
    }

    # Create fleet of 3 drones
    fleet = create_drone_fleet(3, config, small_env)
    assert len(fleet) == 3
    drone_ids = [d.drone_id for d in fleet]
    assert drone_ids == ["DRONE-01", "DRONE-02", "DRONE-03"]

    # All drones have unique starting positions
    positions = [d.position for d in fleet]
    assert len(set(positions)) == 3
    for p in positions:
        assert small_env.is_within_bounds(p)
        assert p not in small_env.obstacles

    # Verify invalid size raises ValueError
    with pytest.raises(ValueError):
        create_drone_fleet(0, config, small_env)
