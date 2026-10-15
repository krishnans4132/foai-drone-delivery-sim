"""server.py

REST API & Web Server for the FOAI Drone Delivery Simulation.
Serves the React Mission Control dashboard and powers real-time simulation controls.
"""

from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Auto-detect workspace virtual environment if running outside it
for _c in [
    Path(__file__).resolve().parents[1] / ".venv" / "bin" / "python",
    Path(__file__).resolve().parent / ".venv" / "bin" / "python",
]:
    if _c.exists() and sys.executable != str(_c) and sys.argv and sys.argv[0].endswith(".py"):
        try:
            import flask  # type: ignore
        except ImportError:
            os.execv(str(_c), [str(_c)] + sys.argv)
        break

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from main import apply_scenario, load_config
from sim.delivery_manager import DeliveryRequest
from sim.planners import AStarPlanner, BFSPlanner, DFSPlanner, UCSPlanner
from sim.search_visualizer import AStarSearchVisualizer, DecisionExplainer
from sim.simulation import Simulation
from sim.test_scenarios import TEST_SCENARIOS

app = Flask(__name__, static_folder="web/dist", static_url_path="")
CORS(app)

CONFIG_PATH = Path(__file__).resolve().parent / "config.json"
BASE_CONFIG = load_config(str(CONFIG_PATH))

# Global simulation state container
class SimSession:
    def __init__(self):
        self.config = copy.deepcopy(BASE_CONFIG)
        self.scenario_name = "default"
        self.active_planner = "A*"
        self.sim = Simulation(self.config, scenario_name=self.scenario_name)
        self.trails: Dict[str, List[List[int]]] = {
            did: [[d.position[0], d.position[1]]] for did, d in self.sim.drones.items()
        }
        self.explainer = DecisionExplainer()
        self.visualizer = AStarSearchVisualizer(self.sim.env, self.sim.weather_agent.current_weather.value)
        self.active_test_id: Optional[str] = None
        self.scheduled_test_events: List[Dict[str, Any]] = []
        self.test_checkpoints: List[Dict[str, Any]] = []

    def reset(self, scenario_name: Optional[str] = None, fleet_size: Optional[int] = None):
        self.active_test_id = None
        self.scheduled_test_events = []
        self.test_checkpoints = []
        if scenario_name:
            self.scenario_name = scenario_name
            cfg = apply_scenario(BASE_CONFIG, scenario_name)
        else:
            cfg = copy.deepcopy(BASE_CONFIG)
            cfg["_scenario_max_ticks"] = 100

        self.config = cfg
        drones_count = fleet_size if fleet_size is not None else cfg.get("fleet", {}).get("num_drones", len(self.sim.drones))
        self.sim = Simulation(self.config, drone_override=drones_count, scenario_name=self.scenario_name)
        self.trails = {
            did: [[d.position[0], d.position[1]]] for did, d in self.sim.drones.items()
        }
        self._apply_planner(self.active_planner)
        self.visualizer = AStarSearchVisualizer(self.sim.env, self.sim.weather_agent.current_weather.value)

    def load_test_scenario(self, scenario_id: str) -> bool:
        if scenario_id not in TEST_SCENARIOS:
            return False
        sc = TEST_SCENARIOS[scenario_id]
        self.active_test_id = scenario_id
        self.scenario_name = sc.get("scenario_name", "default")
        self.scheduled_test_events = copy.deepcopy(sc.get("scheduled_events", []))
        self.test_checkpoints = copy.deepcopy(sc.get("checkpoints", []))

        cfg = copy.deepcopy(BASE_CONFIG)
        if sc.get("scenario_name") and sc["scenario_name"] in BASE_CONFIG.get("scenarios", {}):
            cfg = apply_scenario(BASE_CONFIG, sc["scenario_name"])

        cfg["seed"] = sc.get("seed", 42)
        cfg["_scenario_max_ticks"] = 100
        fleet_count = sc.get("fleet_size", 3)
        cfg.setdefault("fleet", {})["num_drones"] = fleet_count

        if "custom_requests" in sc:
            cfg["delivery_requests"] = [
                {
                    "id": r["id"],
                    "pickup": r["pickup"],
                    "destination": r["destination"],
                    "deadline_ticks": r.get("deadline", 80),
                    "package_weight": 1.0,
                }
                for r in sc["custom_requests"]
            ]

        self.config = cfg
        self.sim = Simulation(self.config, drone_override=fleet_count, scenario_name=self.scenario_name)

        if "initial_weather" in sc:
            self.sim.weather_agent.set_weather(sc["initial_weather"], env=self.sim.env)

        self.trails = {
            did: [[d.position[0], d.position[1]]] for did, d in self.sim.drones.items()
        }
        self._apply_planner(self.active_planner)
        self.visualizer = AStarSearchVisualizer(self.sim.env, self.sim.weather_agent.current_weather.value)
        self.sim.metrics.event_log.log(
            0,
            "SYSTEM",
            f"[TEST SCENARIO LOADED] {sc['title']} active. Ready for live simulation.",
        )
        return True

    def step(self):
        curr_tick = self.sim.current_tick

        # Trigger scheduled scenario events
        if self.scheduled_test_events:
            for ev in self.scheduled_test_events:
                if not ev.get("executed") and curr_tick >= ev.get("tick", 0):
                    ev["executed"] = True
                    act = ev.get("action")
                    if act == "weather":
                        self.sim.weather_agent.set_weather(ev["weather"], env=self.sim.env)
                        self.sim.weather_agent.ticks_since_change = 0
                    elif act == "breakdown":
                        did = ev.get("drone_id") or list(self.sim.drones.keys())[0]
                        self.sim.break_down_drone(did)
                    elif act == "drain_battery":
                        did = ev.get("drone_id") or list(self.sim.drones.keys())[0]
                        self.sim.drain_drone_battery(did, ev.get("pct", 12))
                    elif act == "drain_battery_multi":
                        for did in ev.get("drone_ids", []):
                            self.sim.drain_drone_battery(did, ev.get("pct", 12))
                    elif act == "roadblock_path":
                        placed = False
                        for drone in self.sim.drones.values():
                            if drone.current_path and len(drone.current_path) >= 2:
                                wp = drone.current_path[1]
                                if self.sim.inject_obstacle(wp):
                                    placed = True
                                    break
                        if not placed:
                            free = [(x, y) for y in range(self.sim.env.height) for x in range(self.sim.env.width)
                                    if (x, y) not in set(self.sim.env.obstacles) | set(self.sim.env.charging_stations)]
                            if free:
                                self.sim.inject_obstacle(self.sim.rng.choice(free))
                    if ev.get("log"):
                        self.sim.metrics.event_log.log(curr_tick, "SCENARIO_EVENT", ev["log"])

        self.sim.step()

        for did, drone in self.sim.drones.items():
            pos = [drone.position[0], drone.position[1]]
            trail = self.trails.setdefault(did, [])
            if not trail or trail[-1] != pos:
                trail.append(pos)
                del trail[:-40]  # keep last 40 cells for trail
        for did in list(self.trails):
            if did not in self.sim.drones:
                del self.trails[did]

        # Evaluate test scenario checkpoints
        if self.test_checkpoints:
            for cp in self.test_checkpoints:
                if self.sim.current_tick >= cp.get("min_tick", 0):
                    cp["completed"] = True

    def _apply_planner(self, planner_name: str):
        planners = {"A*": AStarPlanner, "BFS": BFSPlanner, "DFS": DFSPlanner, "UCS": UCSPlanner}
        cls = planners.get(planner_name, AStarPlanner)
        self.active_planner = planner_name
        for drone in self.sim.drones.values():
            drone.planner = cls()

    def serialize(self) -> Dict[str, Any]:
        sim = self.sim
        env = sim.env
        weather = sim.weather_agent.current_weather.value

        # Drones
        drone_list = []
        summary = sim.metrics.get_summary()
        per_drone_metrics = summary.get("per_drone", {})

        for did, drone in sim.drones.items():
            assigned_task_id = drone.assigned_task.id if drone.assigned_task else None
            rem_route = []
            if drone.current_path:
                rem_route = [[c[0], c[1]] for c in drone.current_path]

            dm = per_drone_metrics.get(did, {})
            drone_list.append({
                "id": did,
                "position": [drone.position[0], drone.position[1]],
                "battery": round(drone.battery, 1),
                "batteryCapacity": drone.battery_capacity,
                "batteryPct": round(max(0.0, min(100.0, (drone.battery / drone.battery_capacity) * 100)), 1),
                "state": drone.state.value,
                "hasPackage": drone.has_package,
                "assignedTaskId": assigned_task_id,
                "route": rem_route,
                "trail": self.trails.get(did, []),
                "distanceMoved": dm.get("distance_moved", 0),
                "deliveries": dm.get("deliveries_completed", 0),
                "replans": dm.get("replans_triggered", 0),
                "planner": self.active_planner,
                "isBroken": getattr(drone, "is_broken", False),
            })

        # Requests
        req_list = []
        pending = sim.delivery_manager.pending_requests
        assigned = sim.delivery_manager.assigned_requests
        completed = sim.delivery_manager.completed_requests
        expired = sim.delivery_manager.expired_requests

        for r in pending:
            req_list.append({
                "id": r.id,
                "pickup": [r.pickup[0], r.pickup[1]],
                "destination": [r.destination[0], r.destination[1]],
                "deadline": r.deadline_ticks,
                "assignedDrone": None,
                "status": "WAITING",
            })
        for r in assigned:
            req_list.append({
                "id": r.id,
                "pickup": [r.pickup[0], r.pickup[1]],
                "destination": [r.destination[0], r.destination[1]],
                "deadline": r.deadline_ticks,
                "assignedDrone": r.assigned_drone_id,
                "status": "IN_TRANSIT",
            })
        for r in completed:
            req_list.append({
                "id": r.id,
                "pickup": [r.pickup[0], r.pickup[1]],
                "destination": [r.destination[0], r.destination[1]],
                "deadline": r.deadline_ticks,
                "assignedDrone": r.assigned_drone_id,
                "status": "DELIVERED",
            })
        for r in expired:
            req_list.append({
                "id": r.id,
                "pickup": [r.pickup[0], r.pickup[1]],
                "destination": [r.destination[0], r.destination[1]],
                "deadline": r.deadline_ticks,
                "assignedDrone": r.assigned_drone_id,
                "status": "EXPIRED",
            })

        # Metrics
        ss = summary.get("scenario_summary", {})
        fl = summary.get("fleet", {})
        sf = summary.get("safety", {})
        intel = summary.get("intelligence", {})

        metrics = {
            "deliveriesCompleted": ss.get("deliveries_completed", 0),
            "totalRequests": ss.get("total_requests", 0),
            "deliveriesOnTime": ss.get("deliveries_on_time", 0),
            "completionRatePct": ss.get("completion_rate_pct", 0.0),
            "onTimeRatePct": ss.get("on_time_rate_pct", 0.0),
            "totalDistance": round(fl.get("total_distance_moved", 0), 1),
            "totalBattery": round(fl.get("total_battery_consumed", 0), 1),
            "avgUtilisationPct": fl.get("avg_utilisation_pct", 0.0),
            "collisions": sf.get("collisions", 0),
            "conflictsResolved": sf.get("conflicts_resolved", 0),
            "totalReplans": intel.get("total_replans", 0),
            "fleetSize": len(sim.drones),
        }

        # Event log
        events = sim.metrics.event_log.get_entries()[-25:]

        # Decisions
        decision_lines = self.explainer.latest_assignment(sim.delivery_manager)
        for drone in sim.drones.values():
            if drone.replan_event_log or drone.state.value in ("GOING_TO_CHARGE", "CHARGING"):
                decision_lines += self.explainer.drone_reason(drone, env, weather)
                break

        active_test_info = None
        if self.active_test_id and self.active_test_id in TEST_SCENARIOS:
            sc = TEST_SCENARIOS[self.active_test_id]
            active_test_info = {
                "id": sc["id"],
                "title": sc["title"],
                "category": sc["category"],
                "summary": sc["summary"],
                "objective": sc["objective"],
                "conditions": sc["conditions"],
                "checkpoints": self.test_checkpoints,
                "scheduledEvents": self.scheduled_test_events,
            }

        return {
            "tick": sim.current_tick,
            "seed": sim.seed,
            "scenario": self.scenario_name,
            "weather": weather,
            "planner": self.active_planner,
            "grid": {
                "width": env.width,
                "height": env.height,
                "obstacles": [[c[0], c[1]] for c in env.obstacles],
                "restricted": [[c[0], c[1]] for c in env.restricted_zones],
                "chargers": [[c[0], c[1]] for c in env.charging_stations],
                "starts": [[c[0], c[1]] for c in env.start_locations],
                "stormCells": [[c[0], c[1]] for c in env.active_storm_blocked_cells],
            },
            "drones": drone_list,
            "requests": req_list,
            "metrics": metrics,
            "events": events,
            "decisionExplanation": decision_lines[:8],
            "availableScenarios": list(BASE_CONFIG.get("scenarios", {}).keys()) + ["default"],
            "availablePlanners": ["A*", "BFS", "DFS", "UCS"],
            "activeTestId": self.active_test_id,
            "activeTestInfo": active_test_info,
            "testScenarios": [
                {
                    "id": s["id"],
                    "title": s["title"],
                    "category": s["category"],
                    "summary": s["summary"],
                    "objective": s["objective"],
                    "conditions": s["conditions"],
                }
                for s in TEST_SCENARIOS.values()
            ],
        }


session = SimSession()


@app.route("/api/test/load_scenario", methods=["POST"])
def api_test_load_scenario():
    data = request.get_json(silent=True) or {}
    scenario_id = data.get("scenario_id")
    session.load_test_scenario(scenario_id)
    return jsonify(session.serialize())


# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------

@app.route("/api/state", methods=["GET"])
def api_state():
    return jsonify(session.serialize())


@app.route("/api/step", methods=["POST"])
def api_step():
    data = request.get_json(silent=True) or {}
    ticks = int(data.get("count", 1))
    ticks = max(1, min(ticks, 50))
    for _ in range(ticks):
        session.step()
    return jsonify(session.serialize())


@app.route("/api/reset", methods=["POST"])
def api_reset():
    data = request.get_json(silent=True) or {}
    scenario = data.get("scenario", session.scenario_name)
    fleet_size = data.get("fleet_size")
    if fleet_size is not None:
        fleet_size = int(fleet_size)
    session.reset(scenario_name=scenario, fleet_size=fleet_size)
    return jsonify(session.serialize())


@app.route("/api/weather", methods=["POST"])
def api_weather():
    data = request.get_json(silent=True) or {}
    weather = data.get("weather")
    if weather in ("Clear", "Windy", "Rain", "Storm"):
        prev = session.sim.weather_agent.current_weather.value
        session.sim.weather_agent.set_weather(weather, env=session.sim.env)
        session.sim.weather_agent.ticks_since_change = 0
        if prev != weather:
            session.sim.metrics.record_weather_change(session.sim.current_tick, prev, weather)
    return jsonify(session.serialize())


@app.route("/api/planner", methods=["POST"])
def api_planner():
    data = request.get_json(silent=True) or {}
    planner = data.get("planner")
    if planner in ("A*", "BFS", "DFS", "UCS"):
        session._apply_planner(planner)
    return jsonify(session.serialize())


@app.route("/api/drone/add", methods=["POST"])
def api_drone_add():
    session.sim.add_drone()
    session._apply_planner(session.active_planner)
    return jsonify(session.serialize())


@app.route("/api/drone/remove", methods=["POST"])
def api_drone_remove():
    if len(session.sim.drones) > 1:
        drone_id = next(reversed(session.sim.drones))
        session.sim.remove_drone(drone_id)
    return jsonify(session.serialize())


@app.route("/api/request/add", methods=["POST"])
def api_request_add():
    occupied = set(session.sim.env.obstacles) | set(session.sim.env.restricted_zones)
    occupied |= set(session.sim.env.charging_stations) | set(session.sim.env.active_storm_blocked_cells)
    occupied |= {d.position for d in session.sim.drones.values()}
    free = [
        (x, y) for y in range(session.sim.env.height) for x in range(session.sim.env.width)
        if (x, y) not in occupied and session.sim.env.is_traversable((x, y), session.sim.weather_agent.current_weather.value)
    ]
    if len(free) >= 2:
        pickup, destination = session.sim.rng.sample(free, 2)
        req_num = session.sim.metrics.total_requests + 1
        req = DeliveryRequest(
            id=f"REQ-LIVE-{req_num:03d}",
            pickup=pickup,
            destination=destination,
            deadline_ticks=session.sim.current_tick + 100,
            package_weight=1.0,
        )
        session.sim.delivery_manager.add_request(req)
        session.sim.metrics.total_requests += 1
        session.sim.metrics._request_deadlines[req.id] = req.deadline_ticks
    return jsonify(session.serialize())


# ---------------------------------------------------------------------------
# Test Conditions & Demonstration APIs
# ---------------------------------------------------------------------------

@app.route("/api/test/battery", methods=["POST"])
def api_test_battery():
    data = request.get_json(silent=True) or {}
    drone_id = data.get("drone_id", "all")
    pct = float(data.get("pct", 12.0))
    if drone_id == "all":
        for did in session.sim.drones:
            session.sim.drain_drone_battery(did, pct)
    elif drone_id in session.sim.drones:
        session.sim.drain_drone_battery(drone_id, pct)
    return jsonify(session.serialize())


@app.route("/api/test/breakdown", methods=["POST"])
def api_test_breakdown():
    data = request.get_json(silent=True) or {}
    drone_id = data.get("drone_id")
    action = data.get("action", "break")  # "break" | "repair"
    count = int(data.get("count", 1))

    if action == "repair":
        if drone_id == "all" or not drone_id:
            for did in session.sim.drones:
                session.sim.repair_drone(did)
        elif drone_id in session.sim.drones:
            session.sim.repair_drone(drone_id)
    else:  # "break"
        if drone_id and drone_id in session.sim.drones:
            session.sim.break_down_drone(drone_id)
        else:
            # Pick non-broken drones
            available = [d for d in session.sim.drones.values() if not getattr(d, "is_broken", False)]
            for d in available[:count]:
                session.sim.break_down_drone(d.drone_id)

    return jsonify(session.serialize())


@app.route("/api/test/obstacle", methods=["POST"])
def api_test_obstacle():
    data = request.get_json(silent=True) or {}
    action = data.get("action", "front")  # "front" | "clear" | "pos"
    if action == "clear":
        session.sim.clear_injected_obstacles()
    elif action == "front":
        # Inject dynamic obstacle directly ahead on active drone's path
        injected = False
        for drone in session.sim.drones.values():
            if drone.current_path and len(drone.current_path) >= 2:
                wp = drone.current_path[1]
                if session.sim.inject_obstacle(wp):
                    injected = True
                    break
        if not injected:
            occupied = set(session.sim.env.obstacles) | set(session.sim.env.charging_stations) | {d.position for d in session.sim.drones.values()}
            free = [(x, y) for y in range(session.sim.env.height) for x in range(session.sim.env.width) if (x, y) not in occupied]
            if free:
                pick = session.sim.rng.choice(free)
                session.sim.inject_obstacle(pick)
    else:
        pos = data.get("pos")
        if pos and len(pos) == 2:
            session.sim.inject_obstacle(tuple(pos))

    return jsonify(session.serialize())


@app.route("/api/visualizer/query", methods=["POST"])
def api_visualizer_query():
    data = request.get_json(silent=True) or {}
    start = tuple(data.get("start", [0, 0]))
    goal = tuple(data.get("goal", [19, 19]))
    planner = data.get("planner", "A*")
    weather = session.sim.weather_agent.current_weather.value

    viz = AStarSearchVisualizer(session.sim.env, weather)
    viz.start_search(start, goal)
    steps = 0
    history = []
    while not viz.done and steps < 600:
        c = viz.step()
        if c:
            vals = viz.values(c)
            history.append({
                "cell": [c[0], c[1]],
                "g": round(vals["g"], 1) if vals.get("g") is not None else None,
                "h": round(vals["h"], 1) if vals.get("h") is not None else None,
                "f": round(vals["f"], 1) if vals.get("f") is not None else None,
            })
        steps += 1

    replay_result = None
    if planner in ("BFS", "DFS", "UCS"):
        res = viz.replay(planner)
        replay_result = {
            "name": res.planner_name,
            "cost": round(res.cost, 1),
            "hops": len(res.path),
            "nodesExpanded": res.nodes_expanded,
            "path": [[p[0], p[1]] for p in res.path],
        }

    return jsonify({
        "start": list(start),
        "goal": list(goal),
        "success": viz.success,
        "path": [[p[0], p[1]] for p in viz.path],
        "openSet": [[p[0], p[1]] for p in viz.open_set],
        "closedSet": [[p[0], p[1]] for p in viz.closed_set],
        "expansions": history,
        "replay": replay_result,
    })


# ---------------------------------------------------------------------------
# Static frontend serving
# ---------------------------------------------------------------------------

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_react(path):
    dist_dir = Path(__file__).resolve().parent / "web" / "dist"
    if dist_dir.exists() and (dist_dir / path).exists() and path != "":
        return send_from_directory(str(dist_dir), path)
    if dist_dir.exists() and (dist_dir / "index.html").exists():
        return send_from_directory(str(dist_dir), "index.html")
    return jsonify({
        "message": "Drone Delivery Sim API is running. Vite frontend is in web/ directory.",
        "api_endpoints": ["/api/state", "/api/step", "/api/reset", "/api/weather", "/api/planner"],
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    print(f"\n==================================================================")
    print(f"  FOAI Drone Delivery — Web Server & API")
    print(f"  Serving on: http://localhost:{port}")
    print(f"==================================================================\n")
    app.run(host="0.0.0.0", port=port, debug=False)
