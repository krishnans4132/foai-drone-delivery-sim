"""main.py

Primary entry point for the Simulated Drone Delivery System.
Course: Foundations of Artificial Intelligence (23CSE401)
Team: CB.SC.U4CSE23603 ADWAITH RAVEENDRAN, CB.SC.U4CSE23628 KRISHNAN S, CB.SC.U4CSE23661 MADHAV SREEJITH

Supports:
- User-editable fleet size via:
  1) `num_drones` in config.json
  2) `--drones N` CLI argument (overrides config)
  3) Live interactive modifications in UI ('+' / '-' keys)
- Scenario selection via `--scenario NAME`
- Headless execution via `--headless`
- Seed specification via `--seed SEED`
"""

import argparse
import json
import sys
from pathlib import Path
from sim.simulation import Simulation


def load_config(config_path: str, scenario_name: str | None = None) -> dict:
    """Load configuration from JSON and apply scenario overrides if specified."""
    path = Path(config_path)
    if not path.exists():
        print(f"Error: Config file not found at '{config_path}'.")
        sys.exit(1)

    with open(path, "r") as f:
        config = json.load(f)

    if scenario_name:
        scenarios = config.get("scenarios", {})
        if scenario_name not in scenarios:
            available = ", ".join(scenarios.keys())
            print(f"Error: Unknown scenario '{scenario_name}'. Available scenarios: {available}")
            sys.exit(1)
        scenario = scenarios[scenario_name]
        print(f"Applying scenario '{scenario_name}': {scenario.get('description', '')}")
        if "num_drones" in scenario:
            config["fleet"]["num_drones"] = scenario["num_drones"]
        if "weather_initial" in scenario:
            config["weather"]["initial_weather"] = scenario["weather_initial"]

    return config


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Simulated Drone Delivery System - Multi-Agent A* Path Planning & Task Allocation (FOAI 23CSE401)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--drones",
        type=int,
        default=None,
        metavar="N",
        help="Number of drones in the fleet (overrides config.json and scenario preset; must be >= 1)",
    )
    parser.add_argument(
        "--scenario",
        type=str,
        default=None,
        metavar="NAME",
        help="Preset scenario name (e.g., 'default', 'stormy_rush', 'dense_fleet')",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config.json",
        metavar="PATH",
        help="Path to configuration JSON file",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run simulation in headless mode without graphical UI",
    )
    parser.add_argument(
        "--ticks",
        type=int,
        default=100,
        metavar="T",
        help="Maximum simulation ticks to run (especially for headless mode)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        metavar="S",
        help="RNG seed for reproducibility (overrides config.json)",
    )
    return parser.parse_args()


def main():
    """Main execution function."""
    args = parse_args()
    config = load_config(args.config, args.scenario)

    if args.seed is not None:
        config["seed"] = args.seed

    drone_override = args.drones

    # Validate drone count if provided via CLI
    if drone_override is not None and drone_override < 1:
        print(f"Validation Error: Requested drone count ({drone_override}) must be an integer >= 1.")
        sys.exit(1)

    print("=================================================================")
    print(" Case Study: Simulated Drone Delivery System")
    print(" Course: Foundations of Artificial Intelligence (23CSE401)")
    print(" Team: Adwaith Raveendran, Krishnan S, Madhav Sreejith")
    print("=================================================================")

    sim = Simulation(config, drone_override=drone_override)
    print(f"Grid size: {sim.env.width}x{sim.env.height}")
    print(f"Active Drones: {len(sim.drones)} (Requested: {drone_override or config['fleet']['num_drones']})")
    print(f"Initial Weather: {sim.weather_agent.current_weather.value}")
    print(f"Delivery Requests: {len(sim.delivery_manager.pending_requests)}")

    if args.headless:
        print(f"\nRunning simulation headlessly for {args.ticks} ticks...")
        summary = sim.run_headless(max_ticks=args.ticks)
        print("\nSimulation Finished. Summary Metrics:")
        for k, v in summary.items():
            print(f"  {k}: {v}")
    else:
        print("\nStarting graphical interface (Pygame)...")
        from ui.renderer import UIRenderer
        renderer = UIRenderer(sim)
        renderer.run_loop()


if __name__ == "__main__":
    main()
