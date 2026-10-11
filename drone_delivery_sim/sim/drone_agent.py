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

    def plan_path_to(self, target: Tuple[int, int], env: Any, weather_str: str) -> bool:
        """Execute route planning from current position to target using the configured planner."""
        res = self.planner.search(self.position, target, env, weather=weather_str)
        if res.success and len(res.path) > 1:
            self.current_path = res.path[1:]  # Waypoints excluding current cell
            return True
        elif res.success and len(res.path) == 1:
            self.current_path = []  # Already at target
            return True
        else:
            self.current_path = []
            return False

    def check_and_replan_if_needed(self, target: Tuple[int, int], env: Any, weather_str: str) -> None:
        """Verify current planned trajectory; re-run planner if obstructed by dynamic changes."""
        path_valid = True
        if not self.current_path:
            path_valid = False
        else:
            for cell in self.current_path:
                if not env.is_traversable(cell, weather=weather_str):
                    path_valid = False
                    break

        if not path_valid:
            self.total_replans += 1
            self.plan_path_to(target, env, weather_str)

    # -------------------------------------------------------------------------
    # 3. ACT
    # -------------------------------------------------------------------------
    def step(self, env: Any, weather_str: str) -> DroneAction:
        """Execute one complete Perceive -> Plan -> Act cycle."""
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

            self.check_and_replan_if_needed(self.active_charger_target, env, weather_str)
            return self._follow_path_or_hover(env, weather_str)

        # ---------------------------------------------------------------------
        # State: IDLE
        # ---------------------------------------------------------------------
        if self.state == DroneState.IDLE:
            if self.assigned_task and self.assigned_task.status != "DELIVERED":
                self.state = DroneState.GOING_TO_PICKUP
                self.plan_path_to(self.assigned_task.pickup, env, weather_str)
            elif self.current_path:
                return self._follow_path_or_hover(env, weather_str)
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
                self.plan_path_to(self.assigned_task.destination, env, weather_str)
                return DroneAction.PICKUP

            self.check_and_replan_if_needed(self.assigned_task.pickup, env, weather_str)
            return self._follow_path_or_hover(env, weather_str)

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

            self.check_and_replan_if_needed(self.assigned_task.destination, env, weather_str)
            return self._follow_path_or_hover(env, weather_str)

        # ---------------------------------------------------------------------
        # State: DONE / HOVERING
        # ---------------------------------------------------------------------
        if self.state in (DroneState.DONE, DroneState.HOVERING):
            return self._hover_action(env, weather_str)

        return self._hover_action(env, weather_str)

    # -------------------------------------------------------------------------
    # Internal Movement & Hover Actuators
    # -------------------------------------------------------------------------
    def _follow_path_or_hover(self, env: Any, weather_str: str) -> DroneAction:
        """Step along the active planned route or hover if path is exhausted/blocked."""
        if not self.current_path:
            return self._hover_action(env, weather_str)

        next_pos = self.current_path[0]

        if not env.is_traversable(next_pos, weather=weather_str):
            # Target next cell blocked; cannot step, must hover and wait for replan
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
