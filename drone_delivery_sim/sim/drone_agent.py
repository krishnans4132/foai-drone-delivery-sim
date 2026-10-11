"""sim.drone_agent

Implements the Drone Agent (primary agent in the FOAI Case Study).
Follows the Perceive -> Plan -> Act cycle at each simulation tick.
Sensors:
- Current position (x, y)
- Destination / Target waypoint
- Local obstacle detection (limited sensing radius)
- Battery level (internal state variable, NOT an independent agent)
- Package delivery status
- Current environmental weather

Actuators:
- Move cardinal directions (Up, Down, Left, Right)
- Hover in place
- Pick up package
- Deliver package
- Return to charging station / Charge

Battery Dynamics:
- Internal state variable: battery in [0, battery_capacity].
- Drains per move (higher under Windy/Rain/Storm, plus restricted surcharges).
- Drains on hover.
- Recharges when docked at a charging station.
- Low-battery safety logic: If battery falls below threshold or cannot cover the
  remaining route + safety margin to the nearest charging station, the drone
  detours to the nearest charger, charges up, and resumes its mission.

State Machine:
IDLE, GOING_TO_PICKUP, DELIVERING, GOING_TO_CHARGE, CHARGING, HOVERING, DONE.

Swappable Planners:
Defaults to A* Search (Manhattan heuristic), but accepts any BasePlanner (UCS, BFS, DFS).
"""

from enum import Enum
from typing import Tuple, List, Optional, Set, Dict, Any, Callable
from dataclasses import dataclass, field
import copy

from .planners import BasePlanner, AStarPlanner, manhattan_distance
from .environment import GridEnvironment, PackageEntity


class DroneState(Enum):
    """Internal operational state machine of the Drone Agent."""
    IDLE = "IDLE"
    GOING_TO_PICKUP = "GOING_TO_PICKUP"
    DELIVERING = "DELIVERING"
    GOING_TO_CHARGE = "GOING_TO_CHARGE"
    CHARGING = "CHARGING"
    HOVERING = "HOVERING"
    DONE = "DONE"


class DroneAction(Enum):
    """Actuator commands executed by the drone agent."""
    MOVE_UP = "MOVE_UP"
    MOVE_DOWN = "MOVE_DOWN"
    MOVE_LEFT = "MOVE_LEFT"
    MOVE_RIGHT = "MOVE_RIGHT"
    HOVER = "HOVER"
    PICKUP = "PICKUP"
    DELIVER = "DELIVER"
    CHARGE = "CHARGE"


@dataclass
class DronePerception:
    """Percepts received by the drone agent via its sensors at each tick."""
    current_pos: Tuple[int, int]
    destination: Optional[Tuple[int, int]]
    detected_obstacles: Set[Tuple[int, int]]
    battery_level: float
    package_status: Optional[str]
    current_weather: str
    active_state: DroneState


class DroneAgent:
    """Primary autonomous drone delivery agent.

    Attributes:
        drone_id (str): Unique agent identifier.
        position (Tuple[int, int]): Current 2D grid coordinates.
        battery (float): Current battery charge.
        battery_capacity (float): Maximum battery capacity.
        low_battery_threshold (float): Battery percentage triggering recharge check.
        charge_rate (float): Battery restored per tick spent charging.
        move_cost (float): Base movement energy expenditure.
        hover_cost (float): Energy expended when hovering in place.
        sensor_radius (int): Maximum Chebyshev distance for obstacle perception.
        state (DroneState): Current internal state.
        planner (BasePlanner): Swappable search algorithm (defaults to A*).
        current_path (List[Tuple[int, int]]): Active waypoints to destination.
        assigned_task (Optional[PackageEntity]): Active delivery order.
        has_package (bool): Whether the drone is currently holding the package.
    """

    def __init__(
        self,
        drone_id: str,
        start_pos: Tuple[int, int],
        battery_capacity: float = 100.0,
        low_battery_threshold: float = 25.0,
        charge_rate: float = 15.0,
        move_cost: float = 1.0,
        hover_cost: float = 0.5,
        sensor_radius: int = 4,
        planner: Optional[BasePlanner] = None,
    ):
        """Initialize Drone Agent state, battery, and planner."""
        self.drone_id = drone_id
        self.position = start_pos
        self.battery = float(battery_capacity)
        self.battery_capacity = float(battery_capacity)
        self.low_battery_threshold = float(low_battery_threshold)
        self.charge_rate = float(charge_rate)
        self.move_cost = float(move_cost)
        self.hover_cost = float(hover_cost)
        self.sensor_radius = sensor_radius

        self.state: DroneState = DroneState.IDLE
        self.planner: BasePlanner = planner if planner is not None else AStarPlanner()

        self.current_path: List[Tuple[int, int]] = []
        self.assigned_task: Optional[PackageEntity] = None
        self.has_package: bool = False
        self.completed_tasks: List[PackageEntity] = []

        # Detour memory for resuming delivery after charging
        self.resume_state: Optional[DroneState] = None
        self.resume_target: Optional[Tuple[int, int]] = None
        self.active_charger_target: Optional[Tuple[int, int]] = None

        # Dynamic replanning telemetry & logs
        self.replan_event_log: List[Dict[str, Any]] = []
        self.last_perceived_weather: str = "Clear"
        self.last_planned_cost: float = 0.0
        self.replan_cost_threshold: float = 1.5

        # Telemetry & performance metrics
        self.total_distance_moved: float = 0.0
        self.total_energy_consumed: float = 0.0
        self.total_replans: int = 0

    def set_planner(self, planner: BasePlanner) -> None:
        """Swap the search planner (A*, UCS, BFS, DFS)."""
        self.planner = planner

    def assign_task(self, task: PackageEntity) -> None:
        """Assign a new package delivery task to this drone."""
        self.assigned_task = task
        self.has_package = False
        self.state = DroneState.GOING_TO_PICKUP
        self.current_path = []

    # -------------------------------------------------------------------------
    # 1. PERCEIVE
    # -------------------------------------------------------------------------
    def perceive(self, env: Any, weather_str: str) -> DronePerception:
        """Gather sensor readings within sensor range.

        Sensors: position, destination, obstacle detection (radius), battery,
        package status, current weather.
        """
        dest = None
        if self.state == DroneState.GOING_TO_PICKUP and self.assigned_task:
            dest = self.assigned_task.pickup
        elif self.state == DroneState.DELIVERING and self.assigned_task:
            dest = self.assigned_task.destination
        elif self.state == DroneState.GOING_TO_CHARGE:
            dest = self.active_charger_target

        # Limited sensor radius for obstacle detection
        detected_obs: Set[Tuple[int, int]] = set()
        px, py = self.position
        r = self.sensor_radius
        for ox, oy in env.obstacles:
            if abs(ox - px) <= r and abs(oy - py) <= r:
                detected_obs.add((ox, oy))

        pkg_status = self.assigned_task.status if self.assigned_task else None

        return DronePerception(
            current_pos=self.position,
            destination=dest,
            detected_obstacles=detected_obs,
            battery_level=self.battery,
            package_status=pkg_status,
            current_weather=weather_str,
            active_state=self.state,
        )

    # -------------------------------------------------------------------------
    # 2. PLAN & REPLANNING
    # -------------------------------------------------------------------------
    def _estimate_cost_to_target(self, target: Tuple[int, int], weather_str: str, env: Any) -> float:
        """Estimate energy cost from current position to target."""
        mult = env.weather_cost_multipliers.get(weather_str, 1.0)
        return manhattan_distance(self.position, target) * self.move_cost * mult

    def _estimate_cost_target_to_charger(self, target: Tuple[int, int], weather_str: str, env: Any) -> float:
        """Estimate energy cost from target to nearest charging station."""
        nearest_cs = env.get_nearest_charging_station(target, weather=weather_str)
        if not nearest_cs:
            return 0.0
        mult = env.weather_cost_multipliers.get(weather_str, 1.0)
        return manhattan_distance(target, nearest_cs) * self.move_cost * mult

    def should_divert_for_charge(self, target: Optional[Tuple[int, int]], weather_str: str, env: Any) -> bool:
        """Determine if current battery level necessitates a charging detour.

        Condition:
        Battery <= low_battery_threshold OR cannot cover (remaining_route + target_to_charger + safety_margin).
        """
        if self.state in (DroneState.GOING_TO_CHARGE, DroneState.CHARGING):
            return False

        if not env.charging_stations:
            return False

        # Threshold check
        if self.battery <= self.low_battery_threshold:
            return True

        # Reachability margin check
        if target is not None:
            cost_to_target = self._estimate_cost_to_target(target, weather_str, env)
            cost_to_charger = self._estimate_cost_target_to_charger(target, weather_str, env)
            safety_margin = 10.0  # 10 energy units safety buffer
            if self.battery < (cost_to_target + cost_to_charger + safety_margin):
                return True

        return False

    def plan_path_to(
        self,
        target: Tuple[int, int],
        env: Any,
        weather_str: str,
        blocked_cells: Optional[Set[Tuple[int, int]]] = None,
    ) -> bool:
        """Execute route planning from current position to target using the configured planner."""
        res = self.planner.search(self.position, target, env, weather=weather_str, blocked_cells=blocked_cells)
        if res.success and len(res.path) > 1:
            self.current_path = res.path[1:]  # Waypoints excluding current cell
            self.last_planned_cost = res.cost
            return True
        elif res.success and len(res.path) == 1:
            self.current_path = []  # Already at target
            self.last_planned_cost = 0.0
            return True
        else:
            self.current_path = []
            return False

    def _log_replan_event(self, step_name: str, details: Dict[str, Any]) -> None:
        """Record dynamic replanning step to internal event log."""
        entry = {
            "drone_id": self.drone_id,
            "step": step_name,
            "details": details,
        }
        self.replan_event_log.append(entry)

    # -------------------------------------------------------------------------
    # 4 EXPLICIT DYNAMIC REPLANNING STEPS (FOAI SPECIFICATION)
    # -------------------------------------------------------------------------
    def detect_environmental_change(self, env: Any, current_weather: str) -> Tuple[bool, str]:
        """Step 1: Detect the change.

        Detects if weather state shifted or if any waypoint on the active route
        has become blocked or restricted.
        """
        weather_changed = (current_weather != self.last_perceived_weather)
        reason = ""
        if weather_changed:
            reason = f"Weather shifted from {self.last_perceived_weather} to {current_weather}"
        else:
            for cell in self.current_path:
                if not env.is_traversable(cell, weather=current_weather):
                    reason = f"Cell {cell} along active route became impassable"
                    break

        has_changed = bool(reason)
        self.last_perceived_weather = current_weather
        self._log_replan_event("STEP_1_DETECT_CHANGE", {"has_changed": has_changed, "reason": reason})
        return has_changed, reason

    def detect_change(self, env: Any, current_weather: str) -> Tuple[bool, str]:
        """Alias for Step 1: Detect change."""
        return self.detect_environmental_change(env, current_weather)

    def check_route_suitability(
        self,
        env: Any,
        current_weather: str,
        blocked_cells: Optional[Set[Tuple[int, int]]] = None,
    ) -> Tuple[bool, str]:
        """Step 2: Check whether the current route is still suitable.

        Definition of 'significant change':
        1. A remaining-route cell becomes blocked or restricted under current weather.
        2. The cumulative cost of the remaining route rises above the configurable threshold
           (replan_cost_threshold * baseline_cost).
        """
        if not self.current_path:
            self._log_replan_event("STEP_2_CHECK_SUITABILITY", {"is_suitable": False, "reason": "Path is empty"})
            return False, "Path is empty"

        # Check traversability of all remaining waypoints
        for cell in self.current_path:
            if not env.is_traversable(
                cell, weather=current_weather, blocked_cells=blocked_cells
            ):
                reason = (
                    f"Remaining waypoint {cell} is reserved by another drone"
                    if blocked_cells and cell in blocked_cells
                    else f"Remaining waypoint {cell} is blocked or restricted under {current_weather}"
                )
                self._log_replan_event("STEP_2_CHECK_SUITABILITY", {"is_suitable": False, "reason": reason})
                return False, reason

        # Check cost escalation
        current_remaining_cost = sum(
            env.get_move_cost(
                self.position if i == 0 else self.current_path[i - 1],
                self.current_path[i],
                weather=current_weather,
            )
            for i in range(len(self.current_path))
        )

        if self.last_planned_cost > 0:
            cost_ratio = current_remaining_cost / self.last_planned_cost
            if cost_ratio > self.replan_cost_threshold:
                reason = (
                    f"Route cost escalated beyond threshold: {current_remaining_cost:.2f} vs "
                    f"baseline {self.last_planned_cost:.2f} (ratio {cost_ratio:.2f} > {self.replan_cost_threshold})"
                )
                self._log_replan_event("STEP_2_CHECK_SUITABILITY", {"is_suitable": False, "reason": reason})
                return False, reason

        self._log_replan_event("STEP_2_CHECK_SUITABILITY", {"is_suitable": True, "reason": "Route is clear and within cost bounds"})
        return True, "Route is suitable"

    def recompute_route_astar(
        self,
        target: Tuple[int, int],
        env: Any,
        current_weather: str,
        blocked_cells: Optional[Set[Tuple[int, int]]] = None,
    ) -> bool:
        """Step 3: Run A* again if necessary from current position."""
        res = self.planner.search(self.position, target, env, weather=current_weather, blocked_cells=blocked_cells)
        success = res.success
        if success:
            if len(res.path) > 1:
                self.current_path = res.path[1:]
            else:
                self.current_path = []
            self.last_planned_cost = res.cost
            self.total_replans += 1

        reason = (
            f"A* recomputed path with {len(self.current_path)} waypoints (cost {res.cost:.2f})"
            if success else "A* found no alternative path"
        )
        self._log_replan_event("STEP_3_RECOMPUTE_ASTAR", {
            "success": success,
            "cost": res.cost,
            "nodes_expanded": res.nodes_expanded,
            "reason": reason
        })
        return success

    def run_astar_again(
        self,
        target: Tuple[int, int],
        env: Any,
        current_weather: str,
        blocked_cells: Optional[Set[Tuple[int, int]]] = None,
    ) -> bool:
        """Alias for Step 3: Run A* again."""
        return self.recompute_route_astar(target, env, current_weather, blocked_cells=blocked_cells)

    def continue_with_new_route(self) -> None:
        """Step 4: Continue the delivery using the new route."""
        next_wp = self.current_path[0] if self.current_path else None
        self._log_replan_event("STEP_4_CONTINUE_ROUTE", {
            "next_waypoint": next_wp,
            "remaining_waypoints": len(self.current_path),
        })

    def handle_dynamic_replanning(
        self,
        target: Tuple[int, int],
        env: Any,
        current_weather: str,
        blocked_cells: Optional[Set[Tuple[int, int]]] = None,
    ) -> bool:
        """Execute the 4-step dynamic replanning sequence:
        (1) detect the change
        (2) check whether the current route is still suitable
        (3) run A* again if necessary from current position
        (4) continue with the new route.
        """
        self.detect_environmental_change(env, current_weather)
        is_suitable, _ = self.check_route_suitability(
            env, current_weather, blocked_cells=blocked_cells
        )

        if not is_suitable:
            success = self.recompute_route_astar(target, env, current_weather, blocked_cells=blocked_cells)
            if success:
                self.continue_with_new_route()
                return True
            return False

        return True

    def check_and_replan_if_needed(
        self,
        target: Tuple[int, int],
        env: Any,
        weather_str: str,
        blocked_cells: Optional[Set[Tuple[int, int]]] = None,
    ) -> None:
        """Orchestrate dynamic replanning using the 4 explicit steps."""
        self.handle_dynamic_replanning(target, env, weather_str, blocked_cells=blocked_cells)

    def get_intended_next_position(self) -> Tuple[int, int]:
        """Return the coordinate the drone intends to occupy next tick."""
        if self.state in (DroneState.CHARGING, DroneState.HOVERING, DroneState.DONE):
            return self.position
        if not self.current_path:
            return self.position
        return self.current_path[0]

    # -------------------------------------------------------------------------
    # 3. ACT
    # -------------------------------------------------------------------------
    def step(
        self,
        env: Any,
        weather_str: str,
        override_action: Optional[DroneAction] = None,
        blocked_cells: Optional[Set[Tuple[int, int]]] = None,
    ) -> DroneAction:
        """Execute one complete Perceive -> Plan -> Act cycle."""
        if override_action == DroneAction.HOVER:
            return self._hover_action(env, weather_str)

        perception = self.perceive(env, weather_str)

        # ---------------------------------------------------------------------
        # State: CHARGING
        # ---------------------------------------------------------------------
        if self.state == DroneState.CHARGING:
            # Recharging action at station
            recharge_amount = min(self.charge_rate, self.battery_capacity - self.battery)
            self.battery += recharge_amount

            # If fully charged, resume mission
            if self.battery >= self.battery_capacity - 1e-3:
                self.battery = self.battery_capacity
                if self.resume_state is not None and self.resume_target is not None:
                    self.state = self.resume_state
                    target = self.resume_target
                    self.resume_state = None
                    self.resume_target = None
                    self.plan_path_to(target, env, weather_str)
                else:
                    self.state = DroneState.IDLE
                    self.current_path = []
            return DroneAction.CHARGE

        # ---------------------------------------------------------------------
        # Low Battery Check -> Detour to Nearest Charger
        # ---------------------------------------------------------------------
        active_target = perception.destination
        if self.should_divert_for_charge(active_target, weather_str, env):
            nearest_cs = env.get_nearest_charging_station(self.position, weather=weather_str)
            if blocked_cells:
                available_chargers = [
                    station for station in env.charging_stations
                    if station not in blocked_cells
                    and env.is_traversable(station, weather=weather_str)
                ]
                if available_chargers:
                    nearest_cs = min(
                        available_chargers,
                        key=lambda station: (
                            manhattan_distance(self.position, station), station
                        ),
                    )
            if nearest_cs is not None:
                self.resume_state = self.state
                self.resume_target = active_target
                self.active_charger_target = nearest_cs
                self.state = DroneState.GOING_TO_CHARGE
                self.plan_path_to(nearest_cs, env, weather_str)

        # ---------------------------------------------------------------------
        # State: GOING_TO_CHARGE
        # ---------------------------------------------------------------------
        if self.state == DroneState.GOING_TO_CHARGE:
            if self.position == self.active_charger_target:
                self.state = DroneState.CHARGING
                return DroneAction.CHARGE

            self.check_and_replan_if_needed(
                self.active_charger_target, env, weather_str, blocked_cells=blocked_cells
            )
            return self._follow_path_or_hover(env, weather_str, blocked_cells=blocked_cells)

        # ---------------------------------------------------------------------
        # State: IDLE
        # ---------------------------------------------------------------------
        if self.state == DroneState.IDLE:
            if self.assigned_task and self.assigned_task.status != "DELIVERED":
                self.state = DroneState.GOING_TO_PICKUP
                self.plan_path_to(
                    self.assigned_task.pickup, env, weather_str, blocked_cells=blocked_cells
                )
            elif self.current_path:
                return self._follow_path_or_hover(env, weather_str, blocked_cells=blocked_cells)
            else:
                return self._hover_action(env, weather_str)

        # ---------------------------------------------------------------------
        # State: GOING_TO_PICKUP
        # ---------------------------------------------------------------------
        if self.state == DroneState.GOING_TO_PICKUP:
            if not self.assigned_task:
                self.state = DroneState.IDLE
                return self._hover_action(env, weather_str)

            if self.position == self.assigned_task.pickup:
                # Arrived at pickup: execute pickup actuator
                self.has_package = True
                self.assigned_task.status = "IN_TRANSIT"
                self.state = DroneState.DELIVERING
                self.plan_path_to(
                    self.assigned_task.destination, env, weather_str, blocked_cells=blocked_cells
                )
                return DroneAction.PICKUP

            self.check_and_replan_if_needed(
                self.assigned_task.pickup, env, weather_str, blocked_cells=blocked_cells
            )
            return self._follow_path_or_hover(env, weather_str, blocked_cells=blocked_cells)

        # ---------------------------------------------------------------------
        # State: DELIVERING
        # ---------------------------------------------------------------------
        if self.state == DroneState.DELIVERING:
            if not self.assigned_task:
                self.state = DroneState.IDLE
                return self._hover_action(env, weather_str)

            if self.position == self.assigned_task.destination:
                # Arrived at destination: execute deliver actuator
                self.has_package = False
                self.assigned_task.status = "DELIVERED"
                self.completed_tasks.append(self.assigned_task)
                self.assigned_task = None
                self.state = DroneState.DONE
                return DroneAction.DELIVER

            self.check_and_replan_if_needed(
                self.assigned_task.destination, env, weather_str, blocked_cells=blocked_cells
            )
            return self._follow_path_or_hover(env, weather_str, blocked_cells=blocked_cells)

        # ---------------------------------------------------------------------
        # State: DONE / HOVERING
        # ---------------------------------------------------------------------
        if self.state in (DroneState.DONE, DroneState.HOVERING):
            return self._hover_action(env, weather_str)

        return self._hover_action(env, weather_str)

    # -------------------------------------------------------------------------
    # Internal Movement & Hover Actuators
    # -------------------------------------------------------------------------
    def _follow_path_or_hover(
        self,
        env: Any,
        weather_str: str,
        blocked_cells: Optional[Set[Tuple[int, int]]] = None,
    ) -> DroneAction:
        """Step along the active planned route or hover if path is exhausted/blocked.

        Args:
            blocked_cells: Additional cells to treat as impassable for this tick
                           (e.g. cells reserved by higher-priority drones).
        """
        if not self.current_path:
            return self._hover_action(env, weather_str)

        next_pos = self.current_path[0]

        # Treat as blocked if either environmentally impassable or reserved this tick
        reserved_this_tick = blocked_cells if blocked_cells is not None else set()
        if not env.is_traversable(next_pos, weather=weather_str) or next_pos in reserved_this_tick:
            # Target next cell blocked; hover and wait for replan next tick
            return self._hover_action(env, weather_str)

        # Pop cell and move
        self.current_path.pop(0)
        move_cost = env.get_move_cost(self.position, next_pos, weather=weather_str) * self.move_cost

        dx = next_pos[0] - self.position[0]
        dy = next_pos[1] - self.position[1]
        self.position = next_pos

        self.battery = max(0.0, self.battery - move_cost)
        self.total_distance_moved += 1.0
        self.total_energy_consumed += move_cost

        if dx == 1:
            return DroneAction.MOVE_RIGHT
        elif dx == -1:
            return DroneAction.MOVE_LEFT
        elif dy == 1:
            return DroneAction.MOVE_DOWN
        else:
            return DroneAction.MOVE_UP

    def _hover_action(self, env: Any, weather_str: str) -> DroneAction:
        """Expend hover energy without changing position."""
        mult = env.weather_cost_multipliers.get(weather_str, 1.0)
        drain = self.hover_cost * mult
        self.battery = max(0.0, self.battery - drain)
        self.total_energy_consumed += drain
        return DroneAction.HOVER


# =============================================================================
# Factory Function for Dynamic Drone Fleet Creation
# =============================================================================
def create_drone_fleet(
    num_drones: int,
    config: Dict[str, Any],
    env: Any,
    planner_factory: Optional[Callable[[], BasePlanner]] = None,
) -> List[DroneAgent]:
    """Factory function: Create a fleet of DroneAgent instances.

    The fleet size is never hardcoded. Validates capacity and allocates start cells.

    Args:
        num_drones: Number of drones to initialize (must be >= 1).
        config: Simulation configuration dictionary.
        env: Active GridEnvironment instance.
        planner_factory: Optional callable returning a BasePlanner (defaults to AStarPlanner).

    Returns:
        List of initialized DroneAgent instances.
    """
    if num_drones < 1:
        raise ValueError(f"Requested num_drones ({num_drones}) must be an integer >= 1.")

    # Ensure start locations can accommodate the fleet
    start_positions = env.ensure_start_locations(num_drones, auto_generate=True)

    fleet_cfg = config.get("fleet", {})
    battery_cap = fleet_cfg.get("battery_capacity", 100.0)
    low_bat = fleet_cfg.get("low_battery_threshold", 25.0)
    charge_rate = fleet_cfg.get("charge_rate_per_tick", 15.0)
    move_cost = fleet_cfg.get("move_energy_cost", 1.0)
    hover_cost = fleet_cfg.get("hover_energy_cost", 0.5)

    fleet: List[DroneAgent] = []
    for idx in range(num_drones):
        drone_id = f"DRONE-{idx + 1:02d}"
        pos = start_positions[idx]
        planner = planner_factory() if planner_factory else AStarPlanner()

        drone = DroneAgent(
            drone_id=drone_id,
            start_pos=pos,
            battery_capacity=battery_cap,
            low_battery_threshold=low_bat,
            charge_rate=charge_rate,
            move_cost=move_cost,
            hover_cost=hover_cost,
            planner=planner,
        )
        fleet.append(drone)

    return fleet
