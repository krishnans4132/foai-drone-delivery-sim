"""tests.test_delivery_manager

Unit tests for sim/delivery_manager.py:
- Verification of multi-attribute scoring factors with crafted values:
  - Distance factor (closer drone preferred)
  - Battery factor (higher charge preferred)
  - Workload factor (less loaded drone preferred for load balancing)
  - Availability & insufficient battery disqualification
- Verification that the manager strictly NEVER moves drones
- Verification across fleet sizes: 1, 3, and 8 drones
- Verification of audit log score breakdowns
"""

from pathlib import Path
import pytest

from sim.environment import GridEnvironment
from sim.delivery_manager import DeliveryManagerAgent, DeliveryRequest
from sim.drone_agent import DroneAgent, DroneState, create_drone_fleet


@pytest.fixture
def env():
    """Create a standardized 20x20 grid environment."""
    return GridEnvironment(
        width=20,
        height=20,
        obstacles=[(5, 5)],
        charging_stations=[(0, 0), (19, 19)],
        start_locations=[(0, 0), (1, 0), (2, 0), (3, 0), (4, 0), (5, 0), (6, 0), (7, 0)],
    )


def test_factor_distance_preference(env):
    """Crafted test: Closer drone receives higher distance score and gets assigned."""
    manager = DeliveryManagerAgent()
    req = DeliveryRequest(id="REQ-DIST", pickup=(2, 2), destination=(10, 10), deadline_ticks=100)
    manager.add_request(req)

    # Drone A is at (2, 1) -> Manhattan dist to pickup is 1
    drone_a = DroneAgent(drone_id="DRONE-A", start_pos=(2, 1), battery_capacity=100.0)
    # Drone B is at (18, 18) -> Manhattan dist to pickup is 32
    drone_b = DroneAgent(drone_id="DRONE-B", start_pos=(18, 18), battery_capacity=100.0)

    score_a = manager.score_drone_for_request(drone_a, req, env=env)
    score_b = manager.score_drone_for_request(drone_b, req, env=env)

    assert score_a.distance_score > score_b.distance_score
    assert score_a.total_score > score_b.total_score

    assignments = manager.allocate_requests([drone_a, drone_b], env=env)
    assert assignments.get("DRONE-A") is req
    assert "DRONE-B" not in assignments


def test_factor_battery_preference(env):
    """Crafted test: At equal distance and workload, drone with higher battery is preferred."""
    manager = DeliveryManagerAgent()
    req = DeliveryRequest(id="REQ-BATT", pickup=(5, 5), destination=(10, 10), deadline_ticks=100)
    manager.add_request(req)

    # Both drones at (0, 0)
    drone_a = DroneAgent(drone_id="DRONE-A", start_pos=(0, 0), battery_capacity=100.0)
    drone_a.battery = 95.0

    drone_b = DroneAgent(drone_id="DRONE-B", start_pos=(0, 0), battery_capacity=100.0)
    drone_b.battery = 40.0

    score_a = manager.score_drone_for_request(drone_a, req, env=env)
    score_b = manager.score_drone_for_request(drone_b, req, env=env)

    assert score_a.battery_score > score_b.battery_score
    assert score_a.total_score > score_b.total_score

    assignments = manager.allocate_requests([drone_a, drone_b], env=env)
    assert assignments.get("DRONE-A") is req


def test_factor_workload_sharing(env):
    """Crafted test: At equal distance and battery, less loaded drone is preferred."""
    manager = DeliveryManagerAgent()
    req = DeliveryRequest(id="REQ-WORK", pickup=(5, 5), destination=(10, 10), deadline_ticks=100)
    manager.add_request(req)

    drone_a = DroneAgent(drone_id="DRONE-A", start_pos=(0, 0), battery_capacity=100.0)
    drone_b = DroneAgent(drone_id="DRONE-B", start_pos=(0, 0), battery_capacity=100.0)

    # Simulate drone B having completed 3 deliveries previously
    drone_b.completed_tasks = [DeliveryRequest("P1", (0, 0), (1, 1), 50),
                               DeliveryRequest("P2", (0, 0), (1, 1), 50),
                               DeliveryRequest("P3", (0, 0), (1, 1), 50)]

    score_a = manager.score_drone_for_request(drone_a, req, env=env)
    score_b = manager.score_drone_for_request(drone_b, req, env=env)

    assert score_a.workload_score > score_b.workload_score
    assert score_a.total_score > score_b.total_score

    assignments = manager.allocate_requests([drone_a, drone_b], env=env)
    assert assignments.get("DRONE-A") is req


def test_disqualification_insufficient_battery(env):
    """Crafted test: Drone with insufficient battery to cover route + charger is disqualified."""
    manager = DeliveryManagerAgent()
    req = DeliveryRequest(id="REQ-LOW", pickup=(10, 10), destination=(18, 18), deadline_ticks=100)
    manager.add_request(req)

    drone = DroneAgent(drone_id="DRONE-A", start_pos=(0, 0), battery_capacity=100.0)
    drone.battery = 8.0  # Far too low to reach (10, 10) then (18, 18) then charger

    score = manager.score_drone_for_request(drone, req, env=env)
    assert score.is_eligible is False
    assert "Insufficient battery" in score.disqualification_reason

    assignments = manager.allocate_requests([drone], env=env)
    assert len(assignments) == 0
    assert manager.get_queue_size() == 1  # Stays in queue


def test_manager_never_moves_drones(env):
    """Architectural test: Verify manager has no movement logic and never alters drone positions."""
    manager = DeliveryManagerAgent()
    assert not hasattr(manager, "move_drone")
    assert not hasattr(manager, "step_drone")
    assert not hasattr(manager, "update_position")

    drone_positions_initial = {
        "D1": (0, 0),
        "D2": (5, 5),
        "D3": (10, 10),
    }
    drones = [
        DroneAgent(drone_id=k, start_pos=v, battery_capacity=100.0)
        for k, v in drone_positions_initial.items()
    ]

    req = DeliveryRequest(id="REQ-MOVE", pickup=(1, 1), destination=(8, 8), deadline_ticks=100)
    manager.add_request(req)

    # Execute task allocation
    manager.allocate_requests(drones, env=env)

    # Drone positions must be 100% unchanged
    for d in drones:
        assert d.position == drone_positions_initial[d.drone_id]
        assert len(d.current_path) == 0  # Manager doesn't manipulate path


def test_fleet_sizes_1_3_and_8(env):
    """Verify task allocation functions seamlessly for fleet sizes 1, 3, and 8."""
    config = {
        "fleet": {
            "battery_capacity": 100.0,
            "low_battery_threshold": 25.0,
            "charge_rate_per_tick": 15.0,
            "move_energy_cost": 1.0,
            "hover_energy_cost": 0.5,
        }
    }

    for fleet_size in [1, 3, 8]:
        drones = create_drone_fleet(fleet_size, config, env)
        assert len(drones) == fleet_size

        manager = DeliveryManagerAgent()
        req = DeliveryRequest(id=f"REQ-FLEET-{fleet_size}", pickup=(2, 2), destination=(6, 6), deadline_ticks=50)
        manager.add_request(req)

        assignments = manager.allocate_requests(drones, env=env)
        assert len(assignments) == 1
        assigned_drone_id = next(iter(assignments.keys()))
        assert any(d.drone_id == assigned_drone_id for d in drones)

        # Audit log verification
        latest_event = manager.get_latest_breakdown()
        assert latest_event is not None
        assert latest_event.assigned_drone_id == assigned_drone_id
        assert len(latest_event.candidate_scores) == fleet_size
