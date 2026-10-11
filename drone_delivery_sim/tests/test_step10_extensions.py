import csv
import json
from pathlib import Path

from benchmark_fleet import FIELDS, run_benchmark
from main import load_config
from sim.search_visualizer import AStarSearchVisualizer, DecisionExplainer
from sim.simulation import Simulation
from sim.drone_agent import DroneState
from sim.drone_agent import DroneAgent
from sim.environment import GridEnvironment


ROOT = Path(__file__).resolve().parents[1]


def test_benchmark_writes_documented_csv_json_and_svg(tmp_path):
    config = load_config(str(ROOT / "config.json"))
    rows = run_benchmark(config, "default", [1, 2], seed=91, results_dir=str(tmp_path), max_ticks=3)

    with (tmp_path / "fleet_benchmark.csv").open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == FIELDS
        file_rows = list(reader)
    assert len(file_rows) == 2
    assert [int(row["fleet_size"]) for row in file_rows] == [1, 2]
    assert len(rows) == 2
    payload = json.loads((tmp_path / "fleet_benchmark.json").read_text(encoding="utf-8"))
    assert payload["seed"] == 91
    assert payload["rows"] == rows
    chart = (tmp_path / "fleet_benchmark.svg").read_text(encoding="utf-8")
    assert chart.startswith('<svg xmlns="http://www.w3.org/2000/svg"')
    for label in ("Deliveries", "On-time %", "Avg time", "Distance", "Collisions", "Utilization %"):
        assert label in chart


def _run_seeded(activate_extensions):
    config = load_config(str(ROOT / "config.json"))
    config["seed"] = 2468
    sim = Simulation(config, drone_override=3, scenario_name="default")
    if activate_extensions:
        visualizer = AStarSearchVisualizer(sim.env, sim.weather_agent.current_weather.value)
        visualizer.start_search((0, 0), (6, 4))
        for _ in range(8):
            visualizer.step()
        visualizer.replay("BFS")
        explainer = DecisionExplainer()
        explainer.latest_assignment(sim.delivery_manager)
        for drone in sim.drones.values():
            explainer.drone_reason(drone)
    for _ in range(35):
        sim.step()
    return sim.metrics.get_summary(), sim.metrics.event_log.get_entries()


def test_extensions_do_not_change_same_seed_simulation_results():
    assert _run_seeded(False) == _run_seeded(True)


def test_benchmark_extension_mode_is_seed_reproducible(tmp_path):
    config = load_config(str(ROOT / "config.json"))
    off = run_benchmark(config, "default", [1, 2], 17, str(tmp_path / "off"), 8, extensions_enabled=False)
    on = run_benchmark(config, "default", [1, 2], 17, str(tmp_path / "on"), 8, extensions_enabled=True)
    assert off == on


def test_simulation_tick_allows_charging_drone_to_recharge():
    config = load_config(str(ROOT / "config.json"))
    sim = Simulation(config, drone_override=1)
    drone = next(iter(sim.drones.values()))
    drone.position = sorted(sim.env.charging_stations)[0]
    drone.state = DroneState.CHARGING
    drone.battery = 10.0
    sim._prev_battery[drone.drone_id] = drone.battery

    sim.step()

    assert drone.battery == 25.0
    assert drone.state == DroneState.CHARGING


def test_reserved_next_waypoint_triggers_four_step_replan():
    env = GridEnvironment(width=6, height=6)
    drone = DroneAgent("DRONE-01", (1, 1))
    drone.current_path = [(2, 1), (3, 1), (4, 1)]
    drone.last_planned_cost = 3.0

    replanned = drone.handle_dynamic_replanning(
        (4, 1), env, "Clear", blocked_cells={(2, 1)}
    )

    assert replanned is True
    assert drone.current_path[0] != (2, 1)
    assert [entry["step"] for entry in drone.replan_event_log[-4:]] == [
        "STEP_1_DETECT_CHANGE", "STEP_2_CHECK_SUITABILITY",
        "STEP_3_RECOMPUTE_ASTAR", "STEP_4_CONTINUE_ROUTE",
    ]
