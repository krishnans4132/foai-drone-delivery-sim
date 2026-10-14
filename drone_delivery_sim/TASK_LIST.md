# Project Task List

| Step | Work item | Status | Main references / evidence |
|---|---|---|---|
| 0 | Scaffold, editable configuration, CLI, assumptions, plan, README | Done | `config.json`, `main.py`, `ASSUMPTIONS.md`, `IMPLEMENTATION_PLAN.md`, this list; `python main.py --help` verified. |
| 1 | Grid, entities, traversal/cost rules, config validation | Done | `sim/environment.py`; environment tests in `tests/`. |
| 2 | Seeded four-state weather and override | Done | `sim/weather_agent.py`; weather tests. |
| 3 | A*, BFS, DFS, UCS and comparison output | Done | `sim/planners.py`, `compare_planners.py`, `results/planner_comparison.csv`; planner tests. |
| 4 | Drone state machine, battery, charging, delivery | Done | `sim/drone_agent.py`; drone tests. |
| 5 | Delivery queue, scoring, assignment breakdown | Done | `sim/delivery_manager.py`; manager tests. |
| 6 | Four-stage replanning and collision avoidance | Done | `sim/drone_agent.py`, `sim/simulation.py`; regression tests. |
| 8 | Tick loop, dynamic fleet API, metrics, event logs, scenarios | Done | `sim/simulation.py`, `sim/metrics.py`, `config.json`; seeded outputs in `results/`. |
| 9 | Interactive dashboard, controls, screenshots | Done | `web/`; `results/ui_3_drones.png`, `results/ui_8_drones.png`. |
| 10 | A* visualizer, decision explainer, fleet benchmark | Done | `sim/search_visualizer.py`, `web/`, `benchmark_fleet.py`, `tests/test_step10_extensions.py`. |
| 11 | Full test and scenario verification; six UI captures | Done | 59 tests passed; 36-run CSV/JSON matrix with 0 collisions; `results/screenshots/`. |
| 12 | README, final KI design, traceability and audit | Done | `README.md`, `FOAI Drone Delivery Case Study Spec.md`. |
