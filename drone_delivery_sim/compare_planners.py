"""compare_planners.py

Benchmark suite comparing the 4 search planners specified in the FOAI Case Study:
1. A* Search (Primary planner with Manhattan heuristic: f(n) = g(n) + h(n))
2. Uniform Cost Search (UCS)
3. Breadth-First Search (BFS)
4. Depth-First Search (DFS)

Executes searches on identical start, goal, and weather snapshots.
Writes detailed metrics to results/planner_comparison.csv and displays
a summary comparison table in the console.
"""

import argparse
import csv
import json
from pathlib import Path
from typing import List, Dict, Any, Tuple

from sim.environment import GridEnvironment
from sim.planners import AStarPlanner, UCSPlanner, BFSPlanner, DFSPlanner, SearchResult


def run_benchmark(
    config_path: str = "config.json",
    output_dir: str = "results",
) -> List[Dict[str, Any]]:
    """Execute all four planners across multiple representative routes and weather states."""
    cfg_file = Path(config_path)
    if not cfg_file.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    env = GridEnvironment.from_config(cfg_file)
    with open(cfg_file, "r") as f:
        cfg = json.load(f)

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    csv_file = out_path / "planner_comparison.csv"

    # Define representative benchmark test cases:
    # 1. Delivery Request 1 under Clear weather
    # 2. Delivery Request 2 under Windy weather (increased movement costs)
    # 3. Long-range transit under Rain (restricted cells impassable)
    # 4. Dense obstacle corridor navigation under Storm (high cost, restricted cells impassable)
    test_cases = [
        {
            "id": "REQ-1 (Clear)",
            "start": (2, 5),
            "goal": (18, 18),
            "weather": "Clear",
        },
        {
            "id": "REQ-2 (Windy)",
            "start": (12, 2),
            "goal": (2, 16),
            "weather": "Windy",
        },
        {
            "id": "TRANSIT-3 (Rain)",
            "start": (1, 1),
            "goal": (17, 17),
            "weather": "Rain",
        },
        {
            "id": "CORRIDOR-4 (Storm)",
            "start": (0, 0),
            "goal": (19, 19),
            "weather": "Storm",
        },
    ]

    planners = [
        AStarPlanner(),
        UCSPlanner(),
        BFSPlanner(),
        DFSPlanner(),
    ]

    records: List[Dict[str, Any]] = []

    print("==========================================================================================")
    print("           FOAI 23CSE401 CASE STUDY: SEARCH PLANNERS COMPARATIVE BENCHMARK                ")
    print("==========================================================================================")
    print(f"Grid Layout: {env.width}x{env.height} | Obstacles: {len(env.obstacles)} | Restricted Zones: {len(env.restricted_zones)}")
    print(f"Comparing: A*, UCS, BFS, DFS across {len(test_cases)} scenarios\n")

    for tc in test_cases:
        tc_id = tc["id"]
        start = tc["start"]
        goal = tc["goal"]
        weather = tc["weather"]

        print(f"--- Scenario: {tc_id} | Start: {start} -> Goal: {goal} | Weather: {weather} ---")
        print(f"{'Planner':<8} | {'Success':<8} | {'Path Hops':<10} | {'Path Cost':<10} | {'Nodes Expanded':<16} | {'Runtime (ms)':<12}")
        print("-" * 75)

        for planner in planners:
            res: SearchResult = planner.search(start, goal, env, weather=weather)
            path_hops = len(res.path) - 1 if res.success and len(res.path) > 1 else (0 if res.success else -1)

            record = {
                "scenario": tc_id,
                "planner": res.planner_name,
                "weather": weather,
                "start": f"{start[0]},{start[1]}",
                "goal": f"{goal[0]},{goal[1]}",
                "success": res.success,
                "path_length_hops": path_hops,
                "path_cost": round(res.cost, 2),
                "nodes_expanded": res.nodes_expanded,
                "runtime_ms": round(res.execution_time_ms, 3),
            }
            records.append(record)

            succ_str = "YES" if res.success else "NO"
            print(f"{res.planner_name:<8} | {succ_str:<8} | {path_hops:<10} | {record['path_cost']:<10.2f} | {res.nodes_expanded:<16} | {record['runtime_ms']:<12.3f}")

        print()

    # Write CSV output
    headers = [
        "scenario", "planner", "weather", "start", "goal",
        "success", "path_length_hops", "path_cost", "nodes_expanded", "runtime_ms"
    ]
    with open(csv_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(records)

    print(f"[OK] Full benchmark metrics successfully written to: {csv_file}")
    return records


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark BFS, DFS, UCS, and A* planners for Simulated Drone Delivery System."
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config.json",
        help="Path to config.json (default: config.json)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="results",
        help="Output directory for CSV benchmark results (default: results)",
    )
    args = parser.parse_args()
    run_benchmark(config_path=args.config, output_dir=args.output)


if __name__ == "__main__":
    main()
