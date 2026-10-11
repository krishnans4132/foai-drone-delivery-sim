"""sim.planners

Implements state-space search planners:
1. BFS (Breadth-First Search)
2. DFS (Depth-First Search)
3. UCS (Uniform Cost Search)
4. A* Search (Primary planner with Manhattan distance heuristic: f(n) = g(n) + h(n))

Also provides benchmark metrics tracking (nodes expanded, execution time, path cost, path length).
"""

from typing import Tuple, List, Optional, Callable, Dict, Any
from dataclasses import dataclass
import time


def manhattan_distance(p1: Tuple[int, int], p2: Tuple[int, int]) -> int:
    """Compute Manhattan distance heuristic h(n) = |x1 - x2| + |y1 - y2|."""
    return abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])


@dataclass
class SearchResult:
    """Encapsulates the result and performance metrics of a search planner execution."""
    planner_name: str
    path: List[Tuple[int, int]]
    cost: float
    nodes_expanded: int
    execution_time_ms: float
    success: bool


class BasePlanner:
    """Base interface for all search algorithms."""

    def __init__(self, name: str):
        self.name = name

    def search(
        self,
        start: Tuple[int, int],
        goal: Tuple[int, int],
        env: Any,
        weather: str = "Clear",
        cost_multiplier: float = 1.0,
    ) -> SearchResult:
        """Execute search from start to goal. Must be implemented by subclasses."""
        raise NotImplementedError


class BFSPlanner(BasePlanner):
    """Breadth-First Search: Finds shortest path by hop count; ignores heuristic."""
    def __init__(self):
        super().__init__("BFS")


class DFSPlanner(BasePlanner):
    """Depth-First Search: Rapid deep exploration; non-optimal."""
    def __init__(self):
        super().__init__("DFS")


class UCSPlanner(BasePlanner):
    """Uniform Cost Search: Explores lowest path cost g(n); no heuristic guidance."""
    def __init__(self):
        super().__init__("UCS")


class AStarPlanner(BasePlanner):
    """A* Search: Primary planner combining path cost g(n) and Manhattan heuristic h(n)."""
    def __init__(self):
        super().__init__("A*")
