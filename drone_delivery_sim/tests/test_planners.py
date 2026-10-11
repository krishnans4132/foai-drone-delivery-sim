"""tests.test_planners

Unit tests for sim/planners.py and compare_planners.py:
- A* cost equals UCS cost on weighted grids (optimality verification)
- A* expands no more nodes than UCS (heuristic pruning efficiency: N_A* <= N_UCS)
- No path passes through obstacles, blocked cells, or restricted cells (safety verification)
- Graceful handling of the no-path case (returns success=False, empty path, no crash)
- BFS hop count optimality
- Benchmark execution and CSV output verification
"""

from pathlib import Path
import pytest
from sim.environment import GridEnvironment
from sim.planners import AStarPlanner, UCSPlanner, BFSPlanner, DFSPlanner, SearchResult
from compare_planners import run_benchmark


@pytest.fixture
def test_env():
    """Create a standardized test grid with obstacles and restricted zones."""
    obstacles = [(3, 2), (3, 3), (3, 4), (5, 6), (5, 7), (6, 6)]
    restricted = [(4, 2), (4, 3), (4, 4)]
    return GridEnvironment(
        width=12,
        height=12,
        obstacles=obstacles,
        restricted_zones=restricted,
    )


def test_astar_cost_equals_ucs_cost_weighted_grid(test_env):
    """Verify A* cost exactly matches UCS cost on weighted grids (optimality)."""
    astar = AStarPlanner()
    ucs = UCSPlanner()

    start = (1, 1)
    goal = (8, 8)

    # Test under Clear (restricted zone has surcharge)
    res_astar_clear = astar.search(start, goal, test_env, weather="Clear")
    res_ucs_clear = ucs.search(start, goal, test_env, weather="Clear")

    assert res_astar_clear.success is True
    assert res_ucs_clear.success is True
    assert res_astar_clear.cost == pytest.approx(res_ucs_clear.cost, rel=1e-5)

    # Test under Windy (1.5x multiplier)
    res_astar_windy = astar.search(start, goal, test_env, weather="Windy")
    res_ucs_windy = ucs.search(start, goal, test_env, weather="Windy")

    assert res_astar_windy.success is True
    assert res_ucs_windy.success is True
    assert res_astar_windy.cost == pytest.approx(res_ucs_windy.cost, rel=1e-5)


def test_astar_expands_no_more_nodes_than_ucs(test_env):
    """Verify A* expands no more nodes than UCS due to admissible Manhattan heuristic guidance."""
    astar = AStarPlanner()
    ucs = UCSPlanner()

    test_routes = [
        ((0, 0), (10, 10)),
        ((1, 2), (9, 7)),
        ((2, 8), (11, 2)),
    ]

    for start, goal in test_routes:
        res_a = astar.search(start, goal, test_env, weather="Clear")
        res_u = ucs.search(start, goal, test_env, weather="Clear")

        assert res_a.success is True
        assert res_u.success is True
        assert res_a.nodes_expanded <= res_u.nodes_expanded, (
            f"A* expanded {res_a.nodes_expanded} nodes, exceeding UCS {res_u.nodes_expanded}"
        )


def test_no_path_through_obstacles_blocked_or_restricted(test_env):
    """Verify paths never enter obstacles, storm-blocked cells, or rain-restricted cells."""
    planners = [AStarPlanner(), UCSPlanner(), BFSPlanner(), DFSPlanner()]
    start = (1, 1)
    goal = (7, 5)

    # 1. Under Clear: No path should touch obstacles
    for p in planners:
        res = p.search(start, goal, test_env, weather="Clear")
        assert res.success is True
        for cell in res.path:
            assert cell not in test_env.obstacles, f"{p.name} path entered obstacle: {cell}"

    # 2. Under Rain: Restricted zones are impassable; no path should touch restricted cells
    for p in planners:
        res = p.search(start, goal, test_env, weather="Rain")
        assert res.success is True
        for cell in res.path:
            assert cell not in test_env.obstacles, f"{p.name} path entered obstacle: {cell}"
            assert cell not in test_env.restricted_zones, f"{p.name} path entered restricted zone: {cell}"

    # 3. Dynamic storm blocked cells: No path should touch dynamically blocked cells
    blocked = {(2, 2), (2, 3), (2, 4)}
    for p in planners:
        res = p.search(start, goal, test_env, weather="Storm", blocked_cells=blocked)
        assert res.success is True
        for cell in res.path:
            assert cell not in test_env.obstacles
            assert cell not in test_env.restricted_zones
            assert cell not in blocked, f"{p.name} path entered blocked cell: {cell}"


def test_no_path_case_handled_gracefully():
    """Verify that an unreachable goal is handled gracefully without crashing."""
    # Box in the goal at (5, 5) completely with obstacles: (5,4), (5,6), (4,5), (6,5)
    enclosed_obstacles = [(5, 4), (5, 6), (4, 5), (6, 5)]
    env = GridEnvironment(width=10, height=10, obstacles=enclosed_obstacles)

    start = (0, 0)
    goal = (5, 5)  # completely unreachable

    planners = [AStarPlanner(), UCSPlanner(), BFSPlanner(), DFSPlanner()]

    for p in planners:
        res = p.search(start, goal, env, weather="Clear")
        assert res.success is False
        assert res.path == []
        assert res.cost == 0.0
        assert res.nodes_expanded > 0  # Explored accessible space before failing


def test_start_equals_goal_trivial_case(test_env):
    """Verify start == goal returns a 1-node path with cost 0 and nodes_expanded 0."""
    planners = [AStarPlanner(), UCSPlanner(), BFSPlanner(), DFSPlanner()]
    pos = (2, 2)

    for p in planners:
        res = p.search(pos, pos, test_env, weather="Clear")
        assert res.success is True
        assert res.path == [pos]
        assert res.cost == 0.0
        assert res.nodes_expanded == 0


def test_bfs_finds_minimum_hop_count(test_env):
    """Verify BFS finds path with minimum or equal hop count compared to all planners."""
    bfs = BFSPlanner()
    astar = AStarPlanner()
    dfs = DFSPlanner()

    start = (0, 0)
    goal = (8, 8)

    res_bfs = bfs.search(start, goal, test_env, weather="Clear")
    res_a = astar.search(start, goal, test_env, weather="Clear")
    res_dfs = dfs.search(start, goal, test_env, weather="Clear")

    bfs_hops = len(res_bfs.path) - 1
    a_hops = len(res_a.path) - 1
    dfs_hops = len(res_dfs.path) - 1

    assert bfs_hops <= dfs_hops
    # On grid with uniform step lengths, BFS hops <= A* hops
    assert bfs_hops <= a_hops


def test_run_benchmark_creates_csv(tmp_path):
    """Verify compare_planners.py creates results/planner_comparison.csv correctly."""
    cfg_path = Path(__file__).parent.parent / "config.json"
    records = run_benchmark(config_path=str(cfg_path), output_dir=str(tmp_path))

    csv_file = tmp_path / "planner_comparison.csv"
    assert csv_file.exists()
    assert len(records) == 16  # 4 test cases * 4 planners

    for r in records:
        assert r["success"] is True
        assert r["planner"] in ["A*", "UCS", "BFS", "DFS"]
        assert r["path_length_hops"] > 0
        assert r["path_cost"] > 0.0
