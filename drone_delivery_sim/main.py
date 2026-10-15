"""main.py

Primary entry point for the Simulated Drone Delivery System.
Course: Foundations of Artificial Intelligence (23CSE401)
Team: CB.SC.U4CSE23603 ADWAITH RAVEENDRAN, CB.SC.U4CSE23628 KRISHNAN S, CB.SC.U4CSE23661 MADHAV SREEJITH

Supports:
- User-editable fleet size via:
  1) `num_drones` in config.json
  2) `--drones N` CLI argument (overrides config and scenario preset)
- Scenario selection via `--scenario NAME`
- Headless execution via `--headless`
- Seed specification via `--seed SEED`
- Run all three preset scenarios headless via `--run-all`
"""

import argparse
import copy
import json
import os
import sys
from pathlib import Path

# Ensure UTF-8 output encoding on Windows consoles
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Automatically use the project virtual environment when Flask is unavailable here.
for _c in [
    Path(__file__).resolve().parents[1] / ".venv" / "bin" / "python",
    Path(__file__).resolve().parent / ".venv" / "bin" / "python",
]:
    if _c.exists() and sys.executable != str(_c) and sys.argv and sys.argv[0].endswith(".py"):
        try:
            import flask  # type: ignore
            import flask_cors  # type: ignore
        except ImportError:
            os.execv(str(_c), [str(_c)] + sys.argv)
        break

from sim.simulation import Simulation


# ---------------------------------------------------------------------------
# Config Helpers
# ---------------------------------------------------------------------------

def load_config(config_path: str) -> dict:
    """Load raw configuration from JSON file."""
    path = Path(config_path)
    if not path.exists():
        print(f"Error: Config file not found at '{config_path}'.")
        sys.exit(1)
    with open(path, "r") as f:
        return json.load(f)


def apply_scenario(config: dict, scenario_name: str) -> dict:
    """Deep-copy config and apply scenario overrides.

    Handles:
    - weather_override  : replace weather block
    - extra_requests    : append additional delivery requests
    - num_drones        : set fleet default drone count
    - max_ticks         : exported alongside config for the runner
    """
    scenarios = config.get("scenarios", {})
    if scenario_name not in scenarios:
        available = ", ".join(scenarios.keys())
        print(f"Error: Unknown scenario '{scenario_name}'. Available: {available}")
        sys.exit(1)

    cfg = copy.deepcopy(config)
    scenario = scenarios[scenario_name]

    print(f"\n  Applying scenario '{scenario_name}': {scenario.get('description', '')}")

    if "num_drones" in scenario:
        cfg["fleet"]["num_drones"] = scenario["num_drones"]

    if "weather_override" in scenario:
        wo = scenario["weather_override"]
        cfg["weather"]["initial_weather"] = wo.get(
            "initial_weather", cfg["weather"]["initial_weather"]
        )
        cfg["weather"]["change_interval_ticks"] = wo.get(
            "change_interval_ticks", cfg["weather"]["change_interval_ticks"]
        )
        cfg["weather"]["storm_cells_count"] = wo.get(
            "storm_cells_count", cfg["weather"].get("storm_cells_count", 5)
        )
        if "transition_probabilities" in wo:
            cfg["weather"]["transition_probabilities"] = wo["transition_probabilities"]

    if "extra_requests" in scenario:
        cfg["delivery_requests"] = (
            cfg.get("delivery_requests", []) + scenario["extra_requests"]
        )

    cfg["_scenario_max_ticks"] = scenario.get("max_ticks", 100)
    return cfg


# ---------------------------------------------------------------------------
# Argument Parsing
# ---------------------------------------------------------------------------

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Simulated Drone Delivery System — "
            "Multi-Agent A* Path Planning & Task Allocation (FOAI 23CSE401)"
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--drones", type=int, default=None, metavar="N",
        help="Number of drones (overrides config.json and scenario preset; must be >= 1)",
    )
    parser.add_argument(
        "--scenario", type=str, default=None, metavar="NAME",
        help="Preset scenario name (simple_clear, busy_city, storm_stress, default)",
    )
    parser.add_argument(
        "--config", type=str, default="config.json", metavar="PATH",
        help="Path to configuration JSON file",
    )
    parser.add_argument(
        "--headless", action="store_true",
        help="Run simulation in headless mode without graphical UI",
    )
    parser.add_argument(
        "--ticks", type=int, default=None, metavar="T",
        help="Maximum simulation ticks (overrides scenario default)",
    )
    parser.add_argument(
        "--seed", type=int, default=None, metavar="S",
        help="RNG seed for reproducibility (overrides config.json)",
    )
    parser.add_argument(
        "--run-all", action="store_true",
        help=(
            "Run all three preset scenarios headless with multiple fleet sizes "
            "and print a combined summary table. Implies --headless."
        ),
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Pretty Printing
# ---------------------------------------------------------------------------

def print_banner():
    print("=" * 66)
    print("  Simulated Drone Delivery System")
    print("  Course : Foundations of Artificial Intelligence (23CSE401)")
    print("  Team   : Adwaith Raveendran · Krishnan S · Madhav Sreejith")
    print("=" * 66)


def print_summary(summary: dict, scenario: str, fleet_size: int, ticks: int) -> None:
    """Pretty-print a single scenario run summary."""
    ss = summary["scenario_summary"]
    fl = summary["fleet"]
    sf = summary["safety"]
    intel = summary["intelligence"]

    print(f"\n  ── {scenario.upper()} | {fleet_size} drones | {ticks} ticks ──")
    print(f"  Deliveries : {ss['deliveries_completed']}/{ss['total_requests']} "
          f"completed ({ss['completion_rate_pct']}%)  "
          f"On-time: {ss['deliveries_on_time']} ({ss['on_time_rate_pct']}%)")
    print(f"  Distance   : {fl['total_distance_moved']} cells total  "
          f"({fl['avg_distance_per_drone']} avg/drone)")
    print(f"  Battery    : {fl['total_battery_consumed']} units total  "
          f"({fl['avg_battery_per_drone']} avg/drone)")
    print(f"  Utilisation: {fl['avg_utilisation_pct']}%")
    print(f"  Safety     : {sf['collisions']} collisions  "
          f"{sf['conflicts_resolved']} conflicts resolved")
    print(f"  Replans    : {intel['total_replans']}")

    print("  Per-drone:")
    for did, ds in summary["per_drone"].items():
        print(
            f"    {did}: delivered={ds['deliveries_completed']}  "
            f"dist={ds['distance_moved']}  "
            f"bat={ds['battery_consumed']}  "
            f"replans={ds['replans_triggered']}  "
            f"detours={ds['charge_detours']}  "
            f"util={ds['utilisation_pct']}%"
        )


# ---------------------------------------------------------------------------
# Run-All Helper
# ---------------------------------------------------------------------------

PRESET_SCENARIOS = ["simple_clear", "busy_city", "storm_stress"]
# fleet_sizes[scenario] = [size_A, size_B]  (at least two sizes per scenario)
SCENARIO_FLEET_SIZES = {
    "simple_clear": [2, 4],
    "busy_city":    [3, 6],
    "storm_stress": [4, 8],
}


def run_all_scenarios(base_config: dict, results_dir: str = "results") -> None:
    """Run all three preset scenarios with multiple fleet sizes and export results."""
    os.makedirs(results_dir, exist_ok=True)
    # Clear previous multi-run CSV so we get a clean table
    csv_path = os.path.join(results_dir, "summary.csv")
    if os.path.exists(csv_path):
        os.remove(csv_path)

    all_summaries = []

    for scenario_name in PRESET_SCENARIOS:
        for fleet_size in SCENARIO_FLEET_SIZES[scenario_name]:
            cfg = apply_scenario(base_config, scenario_name)
            if base_config.get("seed"):
                cfg["seed"] = base_config["seed"]
            max_ticks = cfg.get("_scenario_max_ticks", 100)

            # Override fleet size for this run
            cfg["fleet"]["num_drones"] = fleet_size

            run_label = f"{scenario_name}_n{fleet_size}"
            log_path = os.path.join(results_dir, f"event_log_{run_label}.txt")

            print(f"\n  Running: {run_label}  ({max_ticks} ticks) ...", end="", flush=True)
            sim = Simulation(cfg, drone_override=fleet_size, scenario_name=run_label)
            summary = sim.run_headless(
                max_ticks=max_ticks,
                results_dir=results_dir,
                scenario_name=run_label,
            )
            # Write per-run event log with unique name
            sim.metrics.export_event_log(log_path)
            print(" done.")

            all_summaries.append((run_label, fleet_size, max_ticks, summary))

    print("\n" + "=" * 66)
    print("  COMBINED RESULTS")
    print("=" * 66)
    for (sname, fs, ticks, s) in all_summaries:
        print_summary(s, sname, fs, ticks)

    print(f"\n  CSV exported : {os.path.abspath(csv_path)}")
    print(f"  JSON (last)  : {os.path.abspath(os.path.join(results_dir, 'summary.json'))}")
    print(f"  Event logs   : {os.path.abspath(results_dir)}/event_log_*.txt")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    """Main execution function."""
    args = parse_args()
    base_config = load_config(args.config)

    if args.seed is not None:
        base_config["seed"] = args.seed

    if args.drones is not None and args.drones < 1:
        print(f"Validation Error: --drones must be >= 1 (got {args.drones}).")
        sys.exit(1)

    print_banner()

    # ------------------------------------------------------------------
    # The web dashboard is the only interactive interface.
    # ------------------------------------------------------------------
    if not args.headless and not args.run_all:
        from server import app
        port = int(os.environ.get("PORT", 5001))
        print(f"\n==================================================================")
        print(f"  FOAI Drone Delivery — Web Server & API")
        print(f"  Serving React Dashboard on: http://localhost:{port}")
        print(f"==================================================================\n")
        app.run(host="0.0.0.0", port=port, debug=False)
        return

    # ------------------------------------------------------------------
    # --run-all: execute all preset scenarios and show combined table
    # ------------------------------------------------------------------
    if args.run_all:
        run_all_scenarios(base_config)
        return

    # ------------------------------------------------------------------
    # Single scenario / default run
    # ------------------------------------------------------------------
    cfg = base_config
    scenario_name = args.scenario or "default"
    if args.scenario:
        cfg = apply_scenario(base_config, args.scenario)
    else:
        cfg["_scenario_max_ticks"] = 100

    if args.seed is not None:
        cfg["seed"] = args.seed

    drone_override = args.drones
    max_ticks = args.ticks if args.ticks is not None else cfg.get("_scenario_max_ticks", 100)

    sim = Simulation(cfg, drone_override=drone_override, scenario_name=scenario_name)
    print(f"\n  Grid       : {sim.env.width}x{sim.env.height}")
    print(f"  Drones     : {len(sim.drones)}")
    print(f"  Weather    : {sim.weather_agent.current_weather.value}")
    print(f"  Requests   : {len(sim.delivery_manager.pending_requests)}")

    print(f"\n  Running headless for {max_ticks} ticks...", end="", flush=True)
    summary = sim.run_headless(
        max_ticks=max_ticks,
        scenario_name=scenario_name,
    )
    print(" done.")
    print_summary(summary, scenario_name, len(sim.drones), max_ticks)
    print(f"\n  Results written to: {os.path.abspath('results/')}")


if __name__ == "__main__":
    main()
