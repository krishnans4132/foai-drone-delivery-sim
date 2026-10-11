# Architectural Assumptions & Design Decisions

This document tracks all assumptions, simplifications, and design choices made during the implementation of the **Simulated Drone Delivery System**.

| ID | Category | Assumption / Rule | Specification & Rationale |
|---|---|---|---|
| **A-01** | **Fleet Sizing** | Fleet size is dynamic and non-hardcoded ($N \ge 1$). | As specified in ground rules: editable via `config.json`, `--drones N` CLI argument, and live in the UI. When user requests $N$ drones, available starting and charging cells must accommodate them; otherwise, friendly validation feedback is displayed without crashing. |
| **A-02** | **Battery Modeling** | Battery is strictly an internal drone state variable, not an independent agent. | Per spec: battery is a numeric charge state ($0 \le \text{battery} \le \text{battery\_capacity}$). Move and hover actions expend charge; visiting a charging station restores charge. |
| **A-03** | **Grid Coordinate System** | 0-indexed discrete 2D Cartesian grid $[0, \text{width}-1] \times [0, \text{height}-1]$. | Standard discrete grid where moves are cardinal (Up, Down, Left, Right) to adjacent valid cells. Distance metric is Manhattan distance $|x_1 - x_2| + |y_1 - y_2|$. |
| **A-04** | **Weather Impact Levels** | Discrete cost multipliers and traversability rules per weather type. | • **Clear**: base cost ($1.0$).<br>• **Windy**: cost multiplier ($1.5$).<br>• **Rain**: cost multiplier ($2.0$) and restricted cells become impassable.<br>• **Storm**: high cost multiplier ($3.0$) and high-wind corridors/storm cells become temporarily impassable. |
| **A-05** | **Decoupled Architecture** | Core AI simulation in `sim/` has zero dependency on Pygame or UI code. | Enables headless testing, rapid automated evaluation, and CI test runner execution via `pytest`. |
| **A-06** | **RNG Seedability** | All pseudo-randomness flows through an explicit seedable generator instance. | Guarantees deterministic replayability for grading, debugging, and fair planner comparisons. |
| **A-07** | **Dynamic Replanning Trigger** | Drone checks route viability upon weather state changes or cell obstruction. | If current path traverses a cell that becomes restricted/blocked or whose cost escalates beyond `replan_threshold`, A* is re-executed from the drone's current position to its goal. |
