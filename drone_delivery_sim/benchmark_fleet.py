"""Compare delivery performance across fleet sizes.

Example: python benchmark_fleet.py --scenario busy_city --sizes 1 2 4 8 12
Writes a CSV table and dependency-free SVG chart under results/.
"""

from __future__ import annotations

import argparse
import copy
import csv
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from main import apply_scenario, load_config
from sim.simulation import Simulation

FIELDS = [
    "scenario", "seed", "fleet_size", "deliveries_completed", "on_time_rate_pct",
    "average_delivery_time_ticks", "total_distance", "collisions", "utilization_pct",
]


def _delivery_ticks(sim: Simulation) -> List[int]:
    ticks = []
    for line in sim.metrics.event_log.get_entries():
        if "[DELIVERY" in line:
            try:
                ticks.append(int(line.split("]", 1)[0].lstrip("[T")))
            except ValueError:
                continue
    return ticks


def _svg_chart(rows: List[Dict[str, Any]]) -> str:
    width, height, left, top, plot_w, plot_h = 920, 560, 78, 52, 800, 405
    max_size = max((int(r["fleet_size"]) for r in rows), default=1)
    metrics = [
        ("deliveries_completed", "Deliveries", "#55d6a2"),
        ("on_time_rate_pct", "On-time %", "#ffd166"),
        ("average_delivery_time_ticks", "Avg time", "#ff8b6b"),
        ("total_distance", "Distance", "#64aaff"),
        ("collisions", "Collisions", "#f06b82"),
        ("utilization_pct", "Utilization %", "#c59bff"),
    ]
    maximums = {key: max((float(row[key]) for row in rows), default=1.0) or 1.0 for key, _, _ in metrics}
    def point(row, key):
        px = left + (int(row["fleet_size"]) / max_size) * plot_w
        py = top + plot_h - (float(row[key]) / maximums[key]) * plot_h
        return px, py
    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
             '<rect width="100%" height="100%" fill="#101827"/>',
             '<text x="460" y="28" text-anchor="middle" fill="#eef4ff" font-family="Arial" font-size="20">Fleet scaling benchmark</text>']
    for i in range(5):
        y = top + i * plot_h / 4
        lines += [f'<line x1="{left}" y1="{y:.1f}" x2="{left+plot_w}" y2="{y:.1f}" stroke="#304158"/>',
                  f'<text x="{left-12}" y="{y+4:.1f}" text-anchor="end" fill="#aab8ca" font-family="Arial" font-size="11">{100*(4-i)/4:.0f}</text>']
    lines += [f'<line x1="{left}" y1="{top+plot_h}" x2="{left+plot_w}" y2="{top+plot_h}" stroke="#aab8ca"/>',
              f'<text x="{left+plot_w/2}" y="{top+plot_h+42}" text-anchor="middle" fill="#dce6f3" font-family="Arial" font-size="13">Fleet size (drones)</text>',
              f'<text transform="translate(20 {top+plot_h/2}) rotate(-90)" text-anchor="middle" fill="#dce6f3" font-family="Arial" font-size="13">Each metric normalized to its observed maximum (%)</text>']
    for metric, _, color in metrics:
        coords = [point(row, metric) for row in rows]
        lines.append(f'<polyline fill="none" stroke="{color}" stroke-width="2.5" points="{" ".join(f"{x:.1f},{y:.1f}" for x,y in coords)}"/>')
        for x, y in coords:
            lines.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{color}"/>')
    for idx, (_, label, color) in enumerate(metrics):
        col, row_num = idx % 3, idx // 3
        lx = 260 + col * 190
        ly = 494 + row_num * 22
        lines.append(f'<circle cx="{lx}" cy="{ly}" r="5" fill="{color}"/><text x="{lx+12}" y="{ly+4}" fill="#dce6f3" font-family="Arial" font-size="11">{label}</text>')
    lines.append('</svg>')
    return "\n".join(lines)


def run_benchmark(
    config: Dict[str, Any], scenario: str, sizes: Iterable[int], seed: Optional[int] = None,
    results_dir: str = "results", max_ticks: Optional[int] = None,
    extensions_enabled: bool = True,
) -> List[Dict[str, Any]]:
    """Run same seeded scenario for each fleet size and write CSV + SVG.

    ``extensions_enabled`` exists for paired reproducibility checks. Extensions
    only observe the completed run, so it does not alter simulator inputs or ticks.
    """
    fleet_sizes = [int(size) for size in sizes]
    if not fleet_sizes or any(size < 1 for size in fleet_sizes):
        raise ValueError("Provide one or more fleet sizes, each at least 1")
    if scenario == "default":
        base = copy.deepcopy(config)
        base["_scenario_max_ticks"] = 100
    else:
        base = apply_scenario(copy.deepcopy(config), scenario)
    actual_seed = int(seed if seed is not None else config.get("seed", 42))
    base["seed"] = actual_seed
    ticks = max_ticks if max_ticks is not None else int(base.get("_scenario_max_ticks", 100))
    rows = []
    for size in fleet_sizes:
        run_cfg = copy.deepcopy(base)
        run_cfg.setdefault("fleet", {})["num_drones"] = size
        sim = Simulation(run_cfg, drone_override=size, scenario_name=scenario)
        for _ in range(ticks):
            sim.step()
        if extensions_enabled:
            # Run observational tools only after the tick sequence has ended.
            # They own their search state and do not access simulator RNG/state
            # for writes, so toggling this option cannot alter benchmark metrics.
            from sim.search_visualizer import AStarSearchVisualizer, DecisionExplainer
            if sim.env.start_locations and sim.delivery_manager.pending_requests:
                probe = AStarSearchVisualizer(sim.env, sim.weather_agent.current_weather.value)
                probe.start_search(sim.env.start_locations[0], sim.delivery_manager.pending_requests[0].pickup)
                probe.step()
                probe.replay("BFS")
            DecisionExplainer.latest_assignment(sim.delivery_manager)
            for drone in sim.drones.values():
                DecisionExplainer.drone_reason(drone, sim.env, sim.weather_agent.current_weather.value)
        summary = sim.metrics.get_summary()
        delivery_ticks = _delivery_ticks(sim)
        ss, fl = summary["scenario_summary"], summary["fleet"]
        rows.append({
            "scenario": scenario,
            "seed": actual_seed,
            "fleet_size": size,
            "deliveries_completed": ss["deliveries_completed"],
            "on_time_rate_pct": ss["on_time_rate_pct"],
            "average_delivery_time_ticks": round(sum(delivery_ticks) / len(delivery_ticks), 2) if delivery_ticks else 0.0,
            "total_distance": fl["total_distance_moved"],
            "collisions": summary["safety"]["collisions"],
            "utilization_pct": fl["avg_utilisation_pct"],
        })
    os.makedirs(results_dir, exist_ok=True)
    with open(os.path.join(results_dir, "fleet_benchmark.csv"), "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    with open(os.path.join(results_dir, "fleet_benchmark.svg"), "w", encoding="utf-8") as handle:
        handle.write(_svg_chart(rows))
    with open(os.path.join(results_dir, "fleet_benchmark.json"), "w", encoding="utf-8") as handle:
        json.dump({"scenario": scenario, "seed": actual_seed, "rows": rows}, handle, indent=2)
    return rows


def print_table(rows: List[Dict[str, Any]]) -> None:
    print(" | ".join(FIELDS))
    print("-+-".join("-" * len(field) for field in FIELDS))
    for row in rows:
        print(" | ".join(str(row[field]) for field in FIELDS))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", default="simple_clear", choices=("default", "simple_clear", "busy_city", "storm_stress"))
    parser.add_argument("--sizes", type=int, nargs="+", default=[1, 2, 4, 8, 12])
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--ticks", type=int, default=None)
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--results-dir", default="results")
    args = parser.parse_args()
    rows = run_benchmark(load_config(args.config), args.scenario, args.sizes, args.seed, args.results_dir, args.ticks)
    print_table(rows)
    print(f"\nWrote {Path(args.results_dir).resolve()}/fleet_benchmark.csv and fleet_benchmark.svg")


if __name__ == "__main__":
    main()
