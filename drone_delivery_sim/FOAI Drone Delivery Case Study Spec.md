# FOAI Drone Delivery Case Study Spec

**Knowledge Item status:** Final design and Step 12 audit, updated 2026-10-11. This repository file is the maintained local copy of the project KI. The Codex Knowledge Item service is not available as a connected tool in this workspace, so the final design is recorded here for the project team.

## Project and ground rules

Project: **Case Study: Simulated Drone Delivery System**. Course: Foundations of Artificial Intelligence, **23CSE401**, academic year **2026–2027**. Team: **CB.SC.U4CSE23603 ADWAITH RAVEENDRAN**, **CB.SC.U4CSE23628 KRISHNAN S**, **CB.SC.U4CSE23661 MADHAV SREEJITH**.

Implementation uses Python 3.10+, React/Vite for the web dashboard, Flask for its API, pytest for tests, and the standard library for core logic. The `sim/` core is UI-independent and headless-capable. The web dashboard is the only interactive interface; the former Pygame desktop interface has been removed. Fleet size is editable in configuration and live in the dashboard. Scenario fleet values are defaults; fleet requests are validated against available locations and capacity. Random behavior uses explicit seedable RNGs. Ambiguities and implementation choices are documented in `ASSUMPTIONS.md`.

## Specification

### System and agent model

Autonomous drones deliver packages on a grid containing drone starts, pickup/delivery locations, obstacles, restricted cells, charging stations, and dynamic weather. The system has three agent types:

1. **Drone Agent:** perceives its surroundings, plans/routes, picks up and delivers packages, manages battery, avoids obstacles, and replans when conditions change. Battery is an internal state variable, not an agent.
2. **Delivery Manager Agent:** queues delivery requests and assigns each to an available and suitable drone using distance, battery, workload, and availability. It allocates tasks only and does not move drones.
3. **Weather Agent:** introduces stochastic, partially observable weather: Clear (normal cost), Windy (increased movement/energy cost), Rain (higher cost and restricted cells), and Storm (selected cells/routes may be unavailable).

Packages, obstacles, charging stations, and delivery locations are environmental entities, not agents.

### PEAS

- **Performance:** successful and timely delivery, minimum travel distance, efficient battery use, collision avoidance, safe navigation, and effective fleet usage.
- **Environment:** grid delivery area, starts, delivery locations, packages, obstacles, restricted cells, charging stations, other drones, and changing weather.
- **Actuators:** cardinal movement, hover/wait, pickup, delivery, and return to a charging station.
- **Sensors:** position, destination, obstacle/route information, battery, package status, and current weather; no future weather schedule.

### Environment characteristics

Partially Observable (no future changes are exposed); Dynamic (weather, positions, and routes change); Sequential (actions affect later states); Stochastic (weather changes); Discrete (grid cells/actions); Multi-Agent (multiple drones plus manager/weather agents); Known (base map and movement rules are configured and known).

### State-space formulation and search

The valid grid is a graph of cells and legal adjacent moves. Initial state: drone at its start with an assigned task. Actions: move, pickup, deliver, hover/wait, or move toward a charger. Transitions update position, battery, package state, and route. Goal test: delivery at the assigned destination. Path cost is primarily distance with environmental penalties. Use A* with `f(n)=g(n)+h(n)` and Manhattan distance `h(n)=|x_n-x_g|+|y_n-y_g|`; weather only increases movement cost and each move costs at least one, keeping this heuristic admissible. BFS, DFS, and UCS are available for comparison. BFS is suitable for equal edge costs; DFS is not optimal; UCS accounts for variable path cost without heuristic guidance; A* combines path cost and heuristic guidance and can restart from the current cell.

### Battery, allocation, dynamic replanning, and safety

Battery drains on movement and hover, with weather effects, and recharges at stations. A low battery or insufficient remaining energy plus charger safety margin triggers a route to a charger; the drone resumes its task after charging. The task manager evaluates distance, battery, workload, and availability and records score breakdowns. A significant change is a remaining route cell becoming blocked/restricted or route cost increasing beyond the configured threshold. Replanning is explicitly four steps: (1) detect the change, (2) check route suitability, (3) run A* again from current position if needed, (4) continue on the new route. Reservation/waiting and replanning prevent same-cell occupancy and entry into blocked cells.

### Step-by-step project requirements

**Step 0 — Scaffold and plan:** create the project folders/modules, dependency/config files, README, assumptions, implementation plan, and task list; `main.py --help` runs. Required config includes grid, editable fleet, obstacles, chargers, starts, requests/deadlines, weather transitions, battery/move/hover values, threshold, and RNG seed.

**Step 1 — Environment:** grid graph and neighbor function excluding out-of-bounds, obstacles, blocked cells, and weather-restricted moves; environment entities; weather-sensitive move cost; config loading/validation; nearest charger helper; tests for neighbors, obstacles, blocked/restricted cells, and config validation.

**Step 2 — Weather:** exactly four weather states; configurable seedable Markov transitions every N ticks; environment effects and current weather perception without future schedule; manual override; weather effect and deterministic-seed tests.

**Step 3 — Planners:** implement A*, BFS, DFS, UCS without a pathfinding library; return path, cost, and expansion count; comparison driver writes CSV; tests for A*/UCS cost, expansions, forbidden cells, and no path.

**Step 4 — Drone:** perceive/plan/act loop; sensor/actuator scope; move/hover battery drain and charging; charging detour and task resume; IDLE, GOING_TO_PICKUP, DELIVERING, GOING_TO_CHARGE, CHARGING, HOVERING, DONE states; swappable planners; fleet factory; behavior tests.

**Step 5 — Manager:** deadline queue; configurable weighted score over distance, battery, workload, availability; reject unavailable/energy-infeasible drones; assignment score explanation; no movement; any fleet size including one; tests per score factor and fleet sizes 1, 3, 8.

**Step 6 — Replanning and collision avoidance:** four separately named/logged stages; explicit trigger; A* from current cell; collision reservations/wait/replanning; tests for changed routes and zero shared cells across multiple seeds/fleet sizes.

**Step 8 — Simulation, metrics, logs:** tick loop for weather, manager, and drones; headless-capable; runtime `add_drone()`/`remove_drone()` and safe task requeue; total/on-time deliveries, total/per-drone distance, per-drone battery used, collisions, replans, utilization; JSON/CSV summary and detailed event log; three preset scenarios; headless runs with fixed seeds and at least two fleet sizes.

**Step 9 — Interactive UI:** the current interface is the React web dashboard in `web/`, backed by the Flask API in `server.py`. The earlier Pygame desktop interface was removed; dashboard functionality is maintained in the web app.

**Step 10 — Additive unique extension:** (1) animated A* visualizer showing open/closed sets and f/g/h plus BFS/DFS/UCS replay; (2) plain-language assignment/replan/charge decision explanation; (3) user-sized fleet scaling script/UI benchmark producing table/chart for delivery count, on-time rate, average delivery time, distance, collisions, and utilization. Extension modules remain separate; tests cover benchmark format and deterministic simulation parity with extensions enabled/disabled.

**Step 11 — Full verification:** full pytest suite; headless end-to-end for all three scenarios, several seeds and fleet sizes 1, 3, 6, 10; finish all deliveries or explain failures and achieve zero collisions; save six named UI screenshots: route run, storm replan, low-battery detour, A* visualizer, final metrics, live fleet change.

**Step 12 — Documentation and audit:** README overview/team/run instructions, PEAS, all seven environment characteristics with code pointers, state space, A*/Manhattan, allocation, replanning, actual planner comparison CSV results, extension; traceability table; final item-by-item KI audit and final design update.

## Final design

`config.json` is the source for the 20×20 map, fleet defaults, battery values, weather transition matrices, requests, and four scenarios (`default`, `simple_clear`, `busy_city`, `storm_stress`). The CLI supports headless evaluation; the dashboard can add/remove drones while running. The core is split into grid/weather/planners/drone/manager/simulation/metrics modules; the Flask server and React dashboard present the simulation without owning its AI rules. `sim/search_visualizer.py` contains the visualizer and decision explainer logic. `benchmark_fleet.py` creates fresh seeded simulations for each fleet size and exports CSV, JSON, and SVG. The base simulation tick does not call extension search or benchmark logic.

Simulation runs are deterministic for a fixed seed and configuration. Reservation cells are used as dynamic route blockers; a drone's own current cell is allowed as the A* starting state. Removing an active drone returns its request to the queue. Run caps and request deadlines can expire work; metrics and logs record those expirations explicitly.

## Final spec audit

Every requirement group from the original project spec and Steps 0–12 is accounted for. “Done” means implemented and covered by the recorded test or run evidence where that requirement requested verification.

| Spec item | Status | Implementation / evidence |
|---|---|---|
| Ground rules: Python/web dashboard/pytest, headless core, seeded randomness, assumptions | Updated | `requirements.txt`; `web/`; `server.py`; `sim/`; `main.py`; `ASSUMPTIONS.md`; `config.json` and explicit RNGs in `sim/weather_agent.py`, `sim/simulation.py`. |
| Step 0: scaffold/config/CLI and planning artifacts | Done | `config.json`; `main.py` (`parse_args`, `load_config`, `apply_scenario`); `sim/`, `ui/`, `tests/`, `results/`; `IMPLEMENTATION_PLAN.md`, `TASK_LIST.md`, and `README.md`. `python main.py --help` verified. |
| Three agents/four weather states/PEAS | Done | `sim/drone_agent.py` (`DroneAgent`); `sim/delivery_manager.py` (`DeliveryManagerAgent`); `sim/weather_agent.py` (`WeatherAgent`, `WeatherType`); README PEAS and characteristics. |
| Step 1: grid/entities/traversability/config validation/charger lookup | Done | `sim/environment.py` (`GridEnvironment.neighbors`, `is_traversable`, `get_move_cost`, `get_nearest_charging_station`, `from_config`, fleet validation); `tests/`. |
| Step 2: Markov weather, effects, override, reproducibility | Done | `sim/weather_agent.py` (`step`, `_execute_transition`, `apply_to_environment`, `set_weather`); weather tests in `tests/`. |
| Step 3: A*/BFS/DFS/UCS and comparison | Done | `sim/planners.py` (`AStarPlanner`, `BFSPlanner`, `DFSPlanner`, `UCSPlanner`, `manhattan_distance`); `compare_planners.py`; `results/planner_comparison.csv`; planner tests. |
| Step 4: drone perception/actions/state/battery/charge detour | Done | `sim/drone_agent.py` (`DroneAgent.perceive`, `step`, `should_divert_for_charge`, `create_drone_fleet`); drone tests in `tests/`. |
| Step 5: manager allocation and score breakdown, no movement | Done | `sim/delivery_manager.py` (`score_drone_for_request`, `allocate_requests`, assignment history); manager tests in `tests/`. |
| Step 6: named replanning and collision avoidance | Done | `sim/drone_agent.py` (`detect_environmental_change`, `check_route_suitability`, `recompute_route_astar`, `continue_with_new_route`, `handle_dynamic_replanning`); reservations and tick arbitration in `sim/simulation.py`; regression tests. |
| Step 8: tick loop, runtime fleet API, metrics, export, scenarios | Done | `sim/simulation.py` (`step`, `add_drone`, `remove_drone`, `run_headless`); `sim/metrics.py` (`MetricsTracker`, `EventLog` and exports); `config.json`; `results/summary.*`, event logs, `results/step11_headless_matrix.*`. |
| Step 9: UI visuals, panels, controls, help, live fleet | Updated | Current React dashboard in `web/` and Flask API in `server.py`; former Pygame UI removed. Historical screenshots remain under `results/`. |
| Step 10: visualizer, decision explainer, benchmark and parity | Done | `sim/search_visualizer.py` (`AStarSearchVisualizer`, `DecisionExplainer`); `web/`; `benchmark_fleet.py`; `tests/test_step10_extensions.py`; `results/fleet_benchmark.{csv,json,svg}`. |
| Step 11: tests, scenario/seed/fleet matrix, zero collisions, screenshots | Done | Latest suite: 59 passed. Matrix: `results/step11_headless_matrix.csv` and `.json`, 36 runs, 0 collisions. Evidence: `results/screenshots/a_normal_routes.png` through `f_live_fleet_change.png`. |
| Step 12: project guide and final audit | Done | `README.md`; this final spec/KI and traceability audit. |

### Verification findings and deviations

- The 36-run matrix covered `simple_clear`, `busy_city`, and `storm_stress`, with seeds 11, 42, and 2026, and fleet sizes 1, 3, 6, and 10. Of 276 requests, 152 delivered and 124 expired at deadlines by the configured run caps. There were no pending/in-progress requests at the end and **0 collisions**. The expirations in low-fleet and storm-stress cases are expected consequences of the configured request deadlines/run caps and are recorded in the exported results; the acceptance condition allowed incomplete deliveries when explained.
- `results/planner_comparison.csv` has four deterministic query snapshots. The measured planner averages and sample-specific interpretation are in `README.md`; they are not claims about every map or hardware environment.
- Fleet benchmark sample (`simple_clear`, seed 42, sizes 1, 2, 4, 8, 12): completed deliveries were 1, 2, 4, 5, 5 respectively; all completed deliveries were on time and collisions were zero. Full output is in `results/fleet_benchmark.csv` and companion JSON/SVG.
- No unresolved spec item or known behavior deviation remains in the implemented scope. Delivery expiration is reported above rather than hidden. No external Knowledge Item connector was available; this file is the local KI update.
