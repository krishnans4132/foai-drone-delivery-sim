# FOAI Drone Delivery Case Study Spec

## Ground Rules
- **Stack**: Python 3.10+, Pygame (UI), pytest (tests), standard library otherwise. Keep core AI logic separate from the UI so it can run headless.
- **Editable fleet size**: The number of drones must never be hardcoded. It must be user-editable in three ways:
  - (a) a `num_drones` value in `config.json`,
  - (b) a `--drones N` command-line argument that overrides the config, and
  - (c) live in the UI (add or remove drones while the simulation runs).
  - Any integer ≥ 1 is valid, limited only by free start/charging cells. Validate input and show a friendly message if the grid cannot fit the requested number. Preset scenarios have a default count that the user can override.
- **Reproducibility**: All randomness uses a seedable RNG.
- **Spec fidelity**: Never deviate from the spec silently. If something is ambiguous, choose the simplest reading, record it in `ASSUMPTIONS.md`, and continue.
- **Verification**: Verify before reporting done: run the code and tests for each step and show the output.
- **Process cadence**: After each step: summarize what you built, show verification results, update the KI, then STOP and wait for next prompt.

---

## SPEC

### Project Metadata
- **Project**: Case Study: Simulated Drone Delivery System
- **Course**: Foundations of Artificial Intelligence, Code 23CSE401, Academic Year 2026–2027
- **Team**:
  - CB.SC.U4CSE23603 ADWAITH RAVEENDRAN
  - CB.SC.U4CSE23628 KRISHNAN S
  - CB.SC.U4CSE23661 MADHAV SREEJITH

---

### Overview
Autonomous drones transport packages from source locations to destinations in a simulated environment containing delivery locations, obstacles, restricted areas, charging stations, and changing environmental conditions. It is a multi-agent environment with multiple Drone Agents running simultaneously, a Delivery Manager Agent that assigns requests to suitable drones, and a Weather Agent that introduces changing conditions. Each Drone Agent perceives its surroundings, plans a route, monitors its battery, avoids obstacles, and delivers its package. The problem is modeled as a state-space search problem. A* Search is used for route planning, and dynamic replanning handles environment changes.

---

### PEAS Framework
- **Performance Measure**: Successful and timely delivery, minimum travel distance, efficient battery usage, collision avoidance, safe navigation, effective use of available drones.
- **Environment**: Simulated grid-based delivery area with drone start locations, delivery locations, packages, obstacles, restricted cells, charging stations, and changing weather.
- **Actuators**: Move up/down/left/right, hover, pick up package, deliver package, return to charging station.
- **Sensors**: Position, destination, obstacle detection, battery level, package status, current weather.

---

### Environment Characteristics
1. **Partially Observable**: No knowledge of future environmental changes; relies on map and sensors.
2. **Dynamic**: Weather, drone positions, and routes change during execution.
3. **Sequential**: Each move affects position, battery, remaining route.
4. **Stochastic**: Weather changes.
5. **Discrete**: Grid cells.
6. **Multi-Agent**: Multiple drones with different tasks.
7. **Known**: Base map and movement rules are known, dynamic conditions such as weather change.

---

### Agents
1. **Drone Agent**: Primary agent. Navigates to the assigned package, picks it up, plans a route to the destination, avoids obstacles, monitors battery, delivers. If battery is low, goes to a charging station before continuing. If the environment changes, calculates a new route. *Battery is NOT an agent; it is an internal state variable of the Drone Agent.*
2. **Delivery Manager Agent**: Coordinates requests and assigns packages to available drones considering distance to the package, battery level, workload, and availability. It does task allocation only and does not directly control drone movement.
3. **Weather Agent**: Models changing conditions that Drone Agents perceive:
   - **Clear**: Normal movement cost.
   - **Windy**: Increased movement/energy cost.
   - **Rain**: Higher movement cost and restricted cells.
   - **Storm**: Selected routes may become unavailable.

*Note*: Packages, obstacles, and charging stations are environmental entities, not agents.

---

### State-Space Formulation
- **Initial State**: Drone at its starting location with an assigned delivery task.
- **Actions**: Move to an adjacent cell, pick up a package, deliver a package, or move towards a charging station.
- **Transition Model**: An action changes position, battery level, package status, and route.
- **Goal Test**: Package delivered to its assigned destination.
- **Path Cost**: Primarily travel distance, with extra penalties for environmental conditions when required.
- **Graph Representation**: The environment is a graph: valid grid cells are nodes and movement between adjacent cells is an edge.

---

### A* Search & Heuristic
- **Formula**: $f(n) = g(n) + h(n)$
  - $g(n)$: Cost from the start to $n$.
  - $h(n)$: Estimated cost from $n$ to the destination.
- **Heuristic**: Manhattan distance:
  $$h(n) = |x_n - x_g| + |y_n - y_g|$$
- **Rationale**: A* is chosen because it combines incurred cost with estimated remaining cost, so it finds efficient paths while avoiding obstacles and restricted cells.

---

### Task Allocation
For each request, the Delivery Manager Agent considers:
- Distance to the package
- Current battery level
- Current workload
- Drone availability

The drone with the most suitable overall conditions gets the delivery, so multiple drones share the workload.

---

### Dynamic Replanning
When a significant change is detected (for example, rain or a storm makes the selected route unavailable or more costly), the Drone Agent:
1. Detects the change,
2. Checks whether the current route is still suitable,
3. Runs A* again if necessary,
4. Continues the delivery using the new route.

---

### Search Strategy Selection (4 Planners)
1. **BFS (Breadth-First Search)**: Finds a shortest path when all moves cost the same but ignores estimated distance to the goal.
2. **DFS (Depth-First Search)**: May find a path quickly but does not guarantee optimality.
3. **UCS (Uniform Cost Search)**: Handles different path costs but uses no heuristic guidance.
4. **A* Search (Primary)**: Combines actual path cost with a heuristic estimate, suits the grid with Manhattan distance, and can be re-run from the current position when weather changes the route.

---

## Implementation Status
- **Step 0**: Specification established, KI initialized, ground rules codified.
- **Step 1**: Architecture planned, master task list, full directory scaffold, CLI argument parsing, config.json created, pushed to GitHub.
- **Step 2**: Grid graph environment implemented in `sim/environment.py`. Cardinal graph neighbors, obstacle/restricted/blocked cell rules, per-cell move costs with weather multipliers, config loading, dynamic fleet capacity validation & start cell auto-generation, nearest charging station helper. Verified with unit tests.
- **Step 3**: Weather Agent implemented in `sim/weather_agent.py`. Exactly 4 weather conditions (Clear, Windy, Rain, Storm), stochastic Markov transitions every N ticks, seedable RNG reproducibility, dynamic storm-blocked cell generation, direct environmental effect application, strict partial observability (no future schedule exposure), and manual override (`set_weather`). Verified with 9 dedicated unit tests (22 tests total passing).
