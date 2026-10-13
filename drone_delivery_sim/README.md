# FOAI Drone Delivery Case Study

**Course:** Foundations of Artificial Intelligence · **Code:** 23CSE401 · **Academic year:** 2026–2027

**Team**

| Registration number | Name |
|---|---|
| CB.SC.U4CSE23603 | ADWAITH RAVEENDRAN |
| CB.SC.U4CSE23628 | KRISHNAN S |
| CB.SC.U4CSE23661 | MADHAV SREEJITH |

## Overview

This project simulates a fleet of autonomous drones delivering packages on a discrete grid. A drone perceives the current environment, plans and follows routes, manages its battery, and delivers its assigned package. A Delivery Manager allocates requests among available drones; a Weather Agent changes conditions stochastically. Obstacles, restricted cells, charging stations, packages, and delivery points are environment entities, not agents. The simulation core runs headless independently of the Pygame interface.

The primary route planner is A*. The application also provides BFS, DFS, and Uniform Cost Search (UCS), an animated A* visualizer, a decision explanation panel, and a fleet scaling benchmark.

## Requirements and launch

Python 3.10 or newer is required. Install the dependencies and launch the graphical application:

```bash
pip install -r requirements.txt

# Option A: Launch Pygame Desktop GUI
python main.py

# Option B: Launch React Web Mission Control Dashboard (http://localhost:5001)
python main.py --web
```

Set a fleet size from the command line (it overrides the scenario/config default):

```bash
python main.py --drones 8
python main.py --scenario storm_stress --drones 10
```

Available scenario names are `simple_clear`, `busy_city`, `storm_stress`, and `default`. To run without a window, print a summary, and export metrics and the event log:

```bash
python main.py --scenario storm_stress --headless --seed 42 --drones 10
python main.py --headless --run-all
```

The GUI shows the current fleet count. Use **Add drone** and **Remove drone** or the `+` and `-` keys while the simulation is running. Invalid changes display a friendly validation message; removing a drone with an active delivery returns the request to the Manager's queue. Preset drone counts in `config.json` are defaults; `--drones N` overrides them.

Run planner and fleet comparisons, or the automated suite:

```bash
python compare_planners.py
python benchmark_fleet.py --scenario simple_clear --sizes 1 2 4 8 12 --seed 42
pytest -q
```

`benchmark_fleet.py` writes CSV, JSON, and SVG outputs into `results/` by default. The GUI's **Benchmark** tab runs the selected scenario over fleet sizes 1, 2, 4, 8, and 12.

## PEAS

| Element | System description |
|---|---|
| **Performance measure** | Successful and on-time delivery, travel distance, battery use, collision avoidance, safe navigation, and effective fleet utilization. |
| **Environment** | Grid with drone starts, delivery locations, packages, obstacles, restricted cells, charging stations, other drones, and changing weather. |
| **Actuators** | Move up/down/left/right, hover, pick up, deliver, and return to a charging station. |
| **Sensors** | Current position, destination, local obstacle/route information, battery, package status, and current weather. No future weather schedule is exposed. |

## Environment characteristics

| Characteristic | Meaning in this simulation | Code location |
|---|---|---|
| Partially observable | Agents use current perceptions and never receive a future weather schedule. | `WeatherAgent` transitions and current-weather interface: [`sim/weather_agent.py`](sim/weather_agent.py), `weather`, `step`. |
| Dynamic | Weather, drone positions, reservations, and routes can change during a run. | Tick coordination and dynamic replanning: [`sim/simulation.py`](sim/simulation.py), `step`; [`sim/drone_agent.py`](sim/drone_agent.py), `handle_dynamic_replanning`. |
| Sequential | Each action changes position, battery, task state, and subsequent route choices. | Drone action/state transitions: [`sim/drone_agent.py`](sim/drone_agent.py), `step`. |
| Stochastic | Weather transitions are sampled from a configurable Markov table using a seeded RNG. | [`sim/weather_agent.py`](sim/weather_agent.py), `WeatherAgent.step`; transition data in [`config.json`](config.json). |
| Discrete | The world is a finite grid graph with cardinal neighbor moves. | [`sim/environment.py`](sim/environment.py), `GridEnvironment.neighbors`. |
| Multi-agent | Multiple drone agents act with a coordinating manager and a weather agent. | Fleet/tick orchestration: [`sim/simulation.py`](sim/simulation.py), `Simulation.step`; agents in `sim/`. |
| Known | The base map, movement rules, and cost model are configured and available to the system. | [`sim/environment.py`](sim/environment.py), `GridEnvironment.from_config`, `is_traversable`, `get_move_cost`. |

## State-space formulation

The environment is a graph: traversable grid cells are nodes and legal cardinal moves are edges. A planning state includes a drone's current cell and route target; the simulation state also tracks battery, weather, package state, reservations, and assigned task.

- **Initial state:** drone at its start cell with an assigned delivery request.
- **Actions:** move to an adjacent legal cell, pick up a package, deliver it, hover/wait, or route to a charging station.
- **Transition model:** actions update position, battery, package status, and route; weather and reservations can alter legal moves and costs.
- **Goal test:** the assigned package has been delivered to its destination.
- **Path cost:** movement cost begins with distance and adds weather and restricted-cell penalties. Battery cost is tracked separately as an agent resource.

## Route search and heuristic

A* prioritizes `f(n) = g(n) + h(n)`, where `g(n)` is the accumulated route cost and `h(n)` estimates the remaining cost. Its heuristic is Manhattan distance, `h(n) = |x - x_goal| + |y - y_goal|`. Cardinal moves cost at least 1 and weather/restriction effects only add cost, so Manhattan distance is admissible. The search excludes obstacles and currently blocked or forbidden cells. The same planner interface supports UCS, BFS, and DFS; drones use A* by default, and the GUI can switch planners.

### Planner comparison results

These figures are means across the four fixed queries in [`results/planner_comparison.csv`](results/planner_comparison.csv), covering Clear, Windy, Rain, and Storm snapshots. Runtime is measured in milliseconds on this run.

| Planner | Mean path cost | Mean hops | Mean nodes expanded | Mean runtime (ms) |
|---|---:|---:|---:|---:|
| A* | 60.75 | 30.75 | 282.50 | 0.924 |
| UCS | 60.75 | 30.75 | 371.50 | 1.328 |
| BFS | 60.75 | 30.75 | 371.50 | 0.664 |
| DFS | 338.50 | 165.75 | 166.75 | 0.382 |

All four found a path for these queries. A* matched UCS's path costs while expanding fewer nodes on average. BFS matched those costs on this sample; that is specific to these queries and is not a guarantee for nonuniform edge costs. DFS was fastest in this small sample but returned much longer and more expensive paths. Timings are single-run measurements and are hardware/runtime dependent.

## Task allocation and replanning

For each queued request, the Delivery Manager scores eligible drones using distance to pickup, battery, workload, and availability. It records a component-by-component score breakdown and assigns the request to the best candidate. The Manager only allocates work; Drone Agents perform movement and delivery.

When the remaining route becomes blocked/restricted or its cost rises beyond the configured replan threshold, the drone follows four logged steps: (1) detect the change, (2) check whether its current route is still suitable, (3) recompute with A* from its current position when needed, and (4) continue on the new route. Low battery can trigger a charging detour; after charging, the drone resumes its task. Per-tick reservations and waiting/replanning prevent two drones from occupying the same cell.

## User interface

The Pygame view includes a labeled grid and legend, distinct map entity and weather visuals, per-drone colors/IDs, battery and status, carried package, planned route and trail. Side panels show PEAS, weather, fleet status, the request queue, live metrics, and a scrolling event log. Controls include play/pause, step, speed, reset, scenario and planner selection, route visibility, manual weather selection, random request creation, and live fleet changes. The window title contains the project name and course code; About/Help displays team details.

The separate extension tabs provide:

1. **A* Search Visualizer:** click grid cells to choose start/goal; step through open and closed sets and inspect `f`, `g`, and `h`; replay the same query with BFS, DFS, or UCS.
2. **Decision Explainer:** inspect assignment score components and the cause/threshold behind replanning or charging decisions.
3. **Fleet Scaling Benchmark:** compare delivery count, on-time rate, average delivery time, distance, collisions, and utilization across selected fleet sizes; export a table and chart.

The extensions are additive and keep their search/benchmark work outside the simulation tick path.

## Results and verification

The checked-in [`results/step11_headless_matrix.csv`](results/step11_headless_matrix.csv) and JSON record 36 headless runs (three scenarios × three fixed seeds × fleet sizes 1, 3, 6, and 10). Across 276 requests, 152 completed and 124 expired at their deadlines; none remained pending or in progress at the configured run caps, and there were **0 collisions**. The expired requests occur in constrained small-fleet and storm runs and are explicitly counted rather than left unresolved.

The latest full test run for this project reported **59 passed**. The six UI evidence images are in [`results/screenshots/`](results/screenshots/): normal routes, storm replan, charging detour, A* visualizer, final metrics, and live fleet change. The three- and eight-drone UI captures are [`results/ui_3_drones.png`](results/ui_3_drones.png) and [`results/ui_8_drones.png`](results/ui_8_drones.png).

## Project files

| Path | Purpose |
|---|---|
| `main.py` | CLI, config/scenario loading, GUI and headless entry points. |
| `config.json` | Grid, fleet defaults, entities, requests, weather, and scenario presets. |
| `sim/environment.py`, `sim/weather_agent.py` | Grid entities/costs and stochastic weather agent. |
| `sim/planners.py` | A*, UCS, BFS, DFS search implementations and result type. |
| `sim/drone_agent.py`, `sim/delivery_manager.py` | Drone perception/action/battery/replanning and request allocation. |
| `sim/simulation.py`, `sim/metrics.py` | Tick/fleet/collision orchestration, metrics, and event exports. |
| `sim/search_visualizer.py`, `ui/extension_panels.py` | Separate A* visualizer and decision explanation UI. |
| `ui/renderer.py` | Pygame renderer, controls, dashboards, and extension shortcuts. |
| `compare_planners.py`, `benchmark_fleet.py` | Reproducible planner and fleet benchmark drivers. |
| `tests/` | Automated unit/integration and extension regression tests. |
| `results/` | Summaries, event logs, comparison/benchmark data, matrix, and screenshots. |
| `IMPLEMENTATION_PLAN.md`, `TASK_LIST.md` | Overall implementation sequence and completed-step tracker. |
| [`FOAI Drone Delivery Case Study Spec.md`](FOAI%20Drone%20Delivery%20Case%20Study%20Spec.md) | Canonical local KI/spec, final design, and full traceability audit. |

## Traceability

The complete item-by-item audit and file/class/function references are in the canonical local KI at [`FOAI Drone Delivery Case Study Spec.md`](FOAI%20Drone%20Delivery%20Case%20Study%20Spec.md#final-spec-audit). The implementation-to-spec table is maintained there so each requirement has one status and a concrete code or artifact reference.
