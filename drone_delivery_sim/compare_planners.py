"""compare_planners.py

Benchmark suite comparing the 4 search planners specified in the FOAI Case Study:
1. BFS (Breadth-First Search)
2. DFS (Depth-First Search)
3. UCS (Uniform Cost Search)
4. A* Search (Primary planner with Manhattan distance heuristic)

Executes searches across standard test configurations, measuring:
- Nodes expanded
- Path cost and path length
- Execution runtime (ms)
- Completeness and optimality
"""

import argparse
import json
from pathlib import Path
from sim.environment import GridEnvironment
from sim.planners import BFSPlanner, DFSPlanner, UCSPlanner, AStarPlanner


def run_comparison(config_path: str = "config.json", output_dir: str = "results") -> None:
    """Run search planners on configured grid scenarios and output comparison tables."""
    print("================================================================")
    print(" FOAI Case Study: Search Planners Comparative Benchmark")
    print(" Planners: BFS, DFS, UCS, A* (Manhattan heuristic)")
    print("================================================================")

    with open(config_path, "r") as f:
        config = json.load(f)

    print(f"Loaded configuration from: {config_path}")
    print("Benchmarking framework initialized. Detailed planner algorithms in Step 3.")


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark and compare BFS, DFS, UCS, and A* planners for Simulated Drone Delivery."
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config.json",
        help="Path to configuration JSON file (default: config.json)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="results",
        help="Directory to save benchmark metrics and charts (default: results)",
    )
    args = parser.parse_args()
    run_comparison(config_path=args.config, output_dir=args.output)


if __name__ == "__main__":
    main()
