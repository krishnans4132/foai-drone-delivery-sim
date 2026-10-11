"""sim.planners

State-space search planners written from scratch using only Python standard library:
1. A* Search: Primary planner combining path cost g(n) and Manhattan heuristic h(n): f(n) = g(n) + h(n).
2. Uniform Cost Search (UCS): Optimal cost search ordered by g(n).
3. Breadth-First Search (BFS): Shortest hop-count search using FIFO queue.
4. Depth-First Search (DFS): Deep branch exploration using LIFO stack.

All planners share the same graph interface:
search(start, goal, env, weather="Clear", blocked_cells=None) -> SearchResult
"""

from typing import Tuple, List, Optional, Set, Dict, Any
from dataclasses import dataclass
from collections import deque
import heapq
import time


def manhattan_distance(p1: Tuple[int, int], p2: Tuple[int, int]) -> int:
    """Compute Manhattan distance heuristic h(n) = |x1 - x2| + |y1 - y2|."""
    return abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])


@dataclass
class SearchResult:
    """Encapsulates the result and performance metrics of a search planner execution.

    Attributes:
        planner_name (str): Identifier of the algorithm (A*, UCS, BFS, DFS).
        path (List[Tuple[int, int]]): Ordered sequence of coordinates from start to goal.
        cost (float): Total cumulative path cost.
        nodes_expanded (int): Total number of nodes popped from the frontier/open set.
        execution_time_ms (float): Search computation duration in milliseconds.
        success (bool): Whether a valid path to the goal was found.
    """
    planner_name: str
    path: List[Tuple[int, int]]
    cost: float
    nodes_expanded: int
    execution_time_ms: float
    success: bool


def _reconstruct_path(
    came_from: Dict[Tuple[int, int], Tuple[int, int]],
    current: Tuple[int, int],
) -> List[Tuple[int, int]]:
    """Reconstruct path from start to goal using parent pointers."""
    path = [current]
    while current in came_from:
        current = came_from[current]
        path.append(current)
    path.reverse()
    return path


def _compute_path_cost(
    path: List[Tuple[int, int]],
    env: Any,
    weather: str,
) -> float:
    """Calculate the cumulative path cost across consecutive steps in the path."""
    if len(path) <= 1:
        return 0.0
    total = 0.0
    for i in range(len(path) - 1):
        total += env.get_move_cost(path[i], path[i + 1], weather=weather)
    return total


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
        blocked_cells: Optional[Set[Tuple[int, int]]] = None,
    ) -> SearchResult:
        """Execute state-space search from start to goal. Must be implemented by subclasses."""
        raise NotImplementedError


# =============================================================================
# 1. A* Search Planner (Primary)
# =============================================================================
class AStarPlanner(BasePlanner):
    """A* Search: Primary path planner combining incurred path cost g(n) and Manhattan heuristic h(n).

    Formula: f(n) = g(n) + h(n)
    Data Structures:
        - Priority Queue: heapq storing (f(n), counter, node)
        - Closed Set: Set of fully expanded nodes
        - g-score table: Lowest known path cost to each node
        - Parent pointers: Dict mapping child -> parent for path reconstruction
    """

    def __init__(self):
        super().__init__("A*")

    def search(
        self,
        start: Tuple[int, int],
        goal: Tuple[int, int],
        env: Any,
        weather: str = "Clear",
        blocked_cells: Optional[Set[Tuple[int, int]]] = None,
    ) -> SearchResult:
        """Search for the minimum-cost path from start to goal using A*.

        # ---------------------------------------------------------------------
        # ADMISSIBILITY & CONSISTENCY CODE COMMENT:
        # The Manhattan distance heuristic h(n) = |x_n - x_g| + |y_n - y_g| stays
        # admissible and consistent because:
        # 1. On a discrete 4-connected grid without diagonal movement, Manhattan
        #    distance is the exact theoretical minimum step count to reach the goal.
        # 2. Every single move has a base cost >= 1.0 (minimum step cost is 1.0 in Clear).
        # 3. Dynamic weather conditions (Windy: 1.5, Rain: 2.0, Storm: 3.0) and
        #    restricted-cell cautionary surcharges (+1.0) only ADD cost; they never
        #    decrease edge cost below 1.0.
        # Therefore, h(n) * 1.0 never overestimates the actual remaining cost to the goal,
        # guaranteeing that A* finds the optimal (cost-minimal) path while expanding
        # an optimal set of nodes.
        # ---------------------------------------------------------------------
        """
        t0 = time.perf_counter()

        # Edge cases: trivial start == goal or non-traversable endpoints
        if start == goal:
            elapsed = (time.perf_counter() - t0) * 1000.0
            return SearchResult(self.name, [start], 0.0, 0, elapsed, True)

        if not env.is_traversable(start, weather=weather, blocked_cells=blocked_cells) or \
           not env.is_traversable(goal, weather=weather, blocked_cells=blocked_cells):
            elapsed = (time.perf_counter() - t0) * 1000.0
            return SearchResult(self.name, [], 0.0, 0, elapsed, False)

        counter = 0  # Tie-breaker for heapq
        h_start = manhattan_distance(start, goal)
        open_heap: List[Tuple[float, int, Tuple[int, int]]] = [(h_start, counter, start)]
        came_from: Dict[Tuple[int, int], Tuple[int, int]] = {}
        g_score: Dict[Tuple[int, int], float] = {start: 0.0}
        closed_set: Set[Tuple[int, int]] = set()
        nodes_expanded = 0

        while open_heap:
            _, _, current = heapq.heappop(open_heap)

            if current in closed_set:
                continue

            closed_set.add(current)
            nodes_expanded += 1

            if current == goal:
                path = _reconstruct_path(came_from, current)
                cost = g_score[current]
                elapsed = (time.perf_counter() - t0) * 1000.0
                return SearchResult(self.name, path, cost, nodes_expanded, elapsed, True)

            for nbr in env.neighbors(current, weather=weather, blocked_cells=blocked_cells):
                if nbr in closed_set:
                    continue

                move_cost = env.get_move_cost(current, nbr, weather=weather)
                tentative_g = g_score[current] + move_cost

                if tentative_g < g_score.get(nbr, float("inf")):
                    came_from[nbr] = current
                    g_score[nbr] = tentative_g
                    f_score = tentative_g + manhattan_distance(nbr, goal)
                    counter += 1
                    heapq.heappush(open_heap, (f_score, counter, nbr))

        # No path found (disconnected or completely obstructed)
        elapsed = (time.perf_counter() - t0) * 1000.0
        return SearchResult(self.name, [], 0.0, nodes_expanded, elapsed, False)


# =============================================================================
# 2. Uniform Cost Search Planner (UCS)
# =============================================================================
class UCSPlanner(BasePlanner):
    """Uniform Cost Search: Explores nodes ordered strictly by cumulative path cost g(n).

    Equivalent to A* with h(n) = 0. Guarantees optimal cost, but lacks directional heuristic guidance.
    """

    def __init__(self):
        super().__init__("UCS")

    def search(
        self,
        start: Tuple[int, int],
        goal: Tuple[int, int],
        env: Any,
        weather: str = "Clear",
        blocked_cells: Optional[Set[Tuple[int, int]]] = None,
    ) -> SearchResult:
        """Search for the minimum-cost path from start to goal using Dijkstra/UCS."""
        t0 = time.perf_counter()

        if start == goal:
            elapsed = (time.perf_counter() - t0) * 1000.0
            return SearchResult(self.name, [start], 0.0, 0, elapsed, True)

        if not env.is_traversable(start, weather=weather, blocked_cells=blocked_cells) or \
           not env.is_traversable(goal, weather=weather, blocked_cells=blocked_cells):
            elapsed = (time.perf_counter() - t0) * 1000.0
            return SearchResult(self.name, [], 0.0, 0, elapsed, False)

        counter = 0
        open_heap: List[Tuple[float, int, Tuple[int, int]]] = [(0.0, counter, start)]
        came_from: Dict[Tuple[int, int], Tuple[int, int]] = {}
        g_score: Dict[Tuple[int, int], float] = {start: 0.0}
        closed_set: Set[Tuple[int, int]] = set()
        nodes_expanded = 0

        while open_heap:
            current_g, _, current = heapq.heappop(open_heap)

            if current in closed_set:
                continue

            closed_set.add(current)
            nodes_expanded += 1

            if current == goal:
                path = _reconstruct_path(came_from, current)
                cost = g_score[current]
                elapsed = (time.perf_counter() - t0) * 1000.0
                return SearchResult(self.name, path, cost, nodes_expanded, elapsed, True)

            for nbr in env.neighbors(current, weather=weather, blocked_cells=blocked_cells):
                if nbr in closed_set:
                    continue

                move_cost = env.get_move_cost(current, nbr, weather=weather)
                tentative_g = g_score[current] + move_cost

                if tentative_g < g_score.get(nbr, float("inf")):
                    came_from[nbr] = current
                    g_score[nbr] = tentative_g
                    counter += 1
                    heapq.heappush(open_heap, (tentative_g, counter, nbr))

        elapsed = (time.perf_counter() - t0) * 1000.0
        return SearchResult(self.name, [], 0.0, nodes_expanded, elapsed, False)


# =============================================================================
# 3. Breadth-First Search Planner (BFS)
# =============================================================================
class BFSPlanner(BasePlanner):
    """Breadth-First Search: Explores frontier layer-by-layer using a FIFO queue.

    Guarantees shortest path in terms of hop count, but ignores edge cost weights and goal heuristics.
    """

    def __init__(self):
        super().__init__("BFS")

    def search(
        self,
        start: Tuple[int, int],
        goal: Tuple[int, int],
        env: Any,
        weather: str = "Clear",
        blocked_cells: Optional[Set[Tuple[int, int]]] = None,
    ) -> SearchResult:
        """Search for the path with minimum number of steps using BFS."""
        t0 = time.perf_counter()

        if start == goal:
            elapsed = (time.perf_counter() - t0) * 1000.0
            return SearchResult(self.name, [start], 0.0, 0, elapsed, True)

        if not env.is_traversable(start, weather=weather, blocked_cells=blocked_cells) or \
           not env.is_traversable(goal, weather=weather, blocked_cells=blocked_cells):
            elapsed = (time.perf_counter() - t0) * 1000.0
            return SearchResult(self.name, [], 0.0, 0, elapsed, False)

        frontier = deque([start])
        visited: Set[Tuple[int, int]] = {start}
        came_from: Dict[Tuple[int, int], Tuple[int, int]] = {}
        nodes_expanded = 0

        while frontier:
            current = frontier.popleft()
            nodes_expanded += 1

            if current == goal:
                path = _reconstruct_path(came_from, current)
                cost = _compute_path_cost(path, env, weather=weather)
                elapsed = (time.perf_counter() - t0) * 1000.0
                return SearchResult(self.name, path, cost, nodes_expanded, elapsed, True)

            for nbr in env.neighbors(current, weather=weather, blocked_cells=blocked_cells):
                if nbr not in visited:
                    visited.add(nbr)
                    came_from[nbr] = current
                    frontier.append(nbr)

        elapsed = (time.perf_counter() - t0) * 1000.0
        return SearchResult(self.name, [], 0.0, nodes_expanded, elapsed, False)


# =============================================================================
# 4. Depth-First Search Planner (DFS)
# =============================================================================
class DFSPlanner(BasePlanner):
    """Depth-First Search: Explores deep branches using a LIFO stack.

    Non-optimal; may return long meandering paths, but executes rapid single-branch traversal.
    """

    def __init__(self):
        super().__init__("DFS")

    def search(
        self,
        start: Tuple[int, int],
        goal: Tuple[int, int],
        env: Any,
        weather: str = "Clear",
        blocked_cells: Optional[Set[Tuple[int, int]]] = None,
    ) -> SearchResult:
        """Search for a path using DFS."""
        t0 = time.perf_counter()

        if start == goal:
            elapsed = (time.perf_counter() - t0) * 1000.0
            return SearchResult(self.name, [start], 0.0, 0, elapsed, True)

        if not env.is_traversable(start, weather=weather, blocked_cells=blocked_cells) or \
           not env.is_traversable(goal, weather=weather, blocked_cells=blocked_cells):
            elapsed = (time.perf_counter() - t0) * 1000.0
            return SearchResult(self.name, [], 0.0, 0, elapsed, False)

        stack: List[Tuple[int, int]] = [start]
        visited: Set[Tuple[int, int]] = set()
        came_from: Dict[Tuple[int, int], Tuple[int, int]] = {}
        nodes_expanded = 0

        while stack:
            current = stack.pop()

            if current in visited:
                continue

            visited.add(current)
            nodes_expanded += 1

            if current == goal:
                path = _reconstruct_path(came_from, current)
                cost = _compute_path_cost(path, env, weather=weather)
                elapsed = (time.perf_counter() - t0) * 1000.0
                return SearchResult(self.name, path, cost, nodes_expanded, elapsed, True)

            for nbr in env.neighbors(current, weather=weather, blocked_cells=blocked_cells):
                if nbr not in visited:
                    came_from[nbr] = current
                    stack.append(nbr)

        elapsed = (time.perf_counter() - t0) * 1000.0
        return SearchResult(self.name, [], 0.0, nodes_expanded, elapsed, False)
