"""Read-only, incremental search visualisation helpers.

These objects use their own search state and never write to a simulation or its
random number generators.
"""

from __future__ import annotations

import heapq
from typing import Any, Dict, List, Optional, Set, Tuple

from .planners import BFSPlanner, DFSPlanner, UCSPlanner, SearchResult, manhattan_distance

Cell = Tuple[int, int]


class AStarSearchVisualizer:
    """One-expansion-at-a-time A* search with inspectable frontier values."""

    def __init__(self, env: Any, weather: str = "Clear"):
        self.env = env
        self.weather = weather
        self.start: Optional[Cell] = None
        self.goal: Optional[Cell] = None
        self.open_heap: List[Tuple[float, int, Cell]] = []
        self.open_set: Set[Cell] = set()
        self.closed_set: Set[Cell] = set()
        self.g_score: Dict[Cell, float] = {}
        self.f_score: Dict[Cell, float] = {}
        self.came_from: Dict[Cell, Cell] = {}
        self.counter = 0
        self.selected_cell: Optional[Cell] = None
        self.path: List[Cell] = []
        self.done = False
        self.success = False

    def start_search(self, start: Cell, goal: Cell, weather: Optional[str] = None) -> None:
        self.start, self.goal = tuple(start), tuple(goal)
        if weather is not None:
            self.weather = weather
        self.open_heap, self.open_set, self.closed_set = [], set(), set()
        self.g_score, self.f_score, self.came_from = {self.start: 0.0}, {}, {}
        self.counter, self.path, self.done, self.success = 0, [], False, False
        if not (self.env.is_traversable(self.start, self.weather)
                and self.env.is_traversable(self.goal, self.weather)):
            self.done = True
            return
        self.f_score[self.start] = float(manhattan_distance(self.start, self.goal))
        heapq.heappush(self.open_heap, (self.f_score[self.start], self.counter, self.start))
        self.open_set.add(self.start)

    def step(self) -> Optional[Cell]:
        """Expand a single cell and return it; None when no work remains."""
        if self.done:
            return None
        while self.open_heap:
            _, _, current = heapq.heappop(self.open_heap)
            if current not in self.open_set:
                continue
            self.open_set.remove(current)
            self.selected_cell = current
            self.closed_set.add(current)
            if current == self.goal:
                self.path = [current]
                while current in self.came_from:
                    current = self.came_from[current]
                    self.path.append(current)
                self.path.reverse()
                self.done = self.success = True
                return self.selected_cell
            for neighbor in self.env.neighbors(current, weather=self.weather):
                if neighbor in self.closed_set:
                    continue
                tentative = self.g_score[current] + self.env.get_move_cost(
                    current, neighbor, weather=self.weather
                )
                if tentative < self.g_score.get(neighbor, float("inf")):
                    self.came_from[neighbor] = current
                    self.g_score[neighbor] = tentative
                    self.f_score[neighbor] = tentative + manhattan_distance(neighbor, self.goal)
                    self.counter += 1
                    heapq.heappush(self.open_heap, (self.f_score[neighbor], self.counter, neighbor))
                    self.open_set.add(neighbor)
            return self.selected_cell
        self.done = True
        return None

    def values(self, cell: Cell) -> Dict[str, Optional[float]]:
        g = self.g_score.get(cell)
        h = float(manhattan_distance(cell, self.goal)) if self.goal else None
        return {"g": g, "h": h, "f": (g + h) if g is not None and h is not None else None}

    def replay(self, planner: str, blocked_cells=None) -> SearchResult:
        """Solve the current query using BFS, DFS, or UCS for side-by-side study."""
        if self.start is None or self.goal is None:
            raise ValueError("Start a visualizer query before requesting a replay")
        planners = {"BFS": BFSPlanner, "DFS": DFSPlanner, "UCS": UCSPlanner}
        if planner not in planners:
            raise ValueError("Replay planner must be BFS, DFS, or UCS")
        return planners[planner]().search(
            self.start, self.goal, self.env, weather=self.weather, blocked_cells=blocked_cells
        )


class DecisionExplainer:
    """Plain-language, read-only summaries of Manager and drone decisions."""

    @staticmethod
    def latest_assignment(manager: Any) -> List[str]:
        if not manager.assignment_history:
            return ["No Manager assignment has been made yet."]
        event = manager.assignment_history[-1]
        if not event.assigned_drone_id:
            return [f"Request {event.request_id} remains queued because no drone was eligible."]
        chosen = event.candidate_scores[event.assigned_drone_id]
        lines = [f"Request {event.request_id} went to {event.assigned_drone_id} (score {chosen.total_score:.3f})."]
        labels = (
            ("distance", chosen.distance_score, "closer pickup"),
            ("battery", chosen.battery_score, "battery reserve"),
            ("workload", chosen.workload_score, "lighter workload"),
            ("availability", chosen.availability_score, "availability"),
        )
        lines.extend(f"• {label.title()}: {score:.2f} ({why})." for label, score, why in labels)
        for drone_id, score in event.candidate_scores.items():
            if drone_id != event.assigned_drone_id and score.is_eligible:
                lines.append(f"{drone_id} scored {score.total_score:.3f}.")
            elif not score.is_eligible:
                lines.append(f"{drone_id} was skipped: {score.disqualification_reason or 'not eligible'}.")
        return lines

    @staticmethod
    def drone_reason(drone: Any, env: Any = None, weather: str = "Clear") -> List[str]:
        lines: List[str] = []
        if drone.replan_event_log:
            entries = drone.replan_event_log[-4:]
            for entry in entries:
                step = entry.get("step", "")
                details = entry.get("details", {})
                if step == "STEP_1_DETECT_CHANGE":
                    lines.append(f"Step 1 detected a route change: {details.get('reason', 'environment changed')}.")
                elif step == "STEP_2_CHECK_SUITABILITY":
                    reason = details.get("reason", "route suitability checked")
                    lines.append(f"Step 2 checked the route: {reason}.")
                elif step == "STEP_3_RECOMPUTE_ASTAR":
                    lines.append(f"Step 3 ran A* again: {details.get('reason', 'route recomputed')}.")
                elif step == "STEP_4_CONTINUE_ROUTE":
                    lines.append("Step 4 continued on the updated route.")
        if getattr(drone, "state", None) is not None and getattr(drone.state, "value", "") in ("GOING_TO_CHARGE", "CHARGING"):
            threshold = getattr(drone, "low_battery_threshold", None)
            if threshold is not None and drone.battery <= threshold:
                lines.append(f"{drone.drone_id} diverted because battery {drone.battery:.1f} crossed the low-battery threshold ({threshold:.1f}).")
            elif env is not None and drone.resume_target is not None:
                to_target = drone._estimate_cost_to_target(drone.resume_target, weather, env)
                to_charger = drone._estimate_cost_target_to_charger(drone.resume_target, weather, env)
                needed = to_target + to_charger + 10.0
                lines.append(f"{drone.drone_id} diverted because {drone.battery:.1f} battery could not cover the route + charger + 10.0 safety reserve ({needed:.1f} needed).")
            else:
                lines.append(f"{drone.drone_id} is heading to a charging station; battery is {drone.battery:.1f} and low-battery threshold is {threshold}.")
            if getattr(drone, "resume_target", None) is not None:
                lines.append(f"It will resume toward {drone.resume_target} after charging.")
        return lines or [f"{drone.drone_id} has no recent replan or charging decision."]
