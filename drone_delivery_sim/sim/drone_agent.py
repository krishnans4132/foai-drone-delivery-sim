"""sim.drone_agent

Implements the Drone Agent (primary agent).
Perceives surroundings, monitors internal battery level, plans routes using A*,
executes actuators (move, hover, pick up, deliver, recharge), avoids obstacles,
and performs dynamic replanning when environmental conditions (weather, obstacles) shift.
Note: Battery is an internal state variable of DroneAgent, NOT an agent.
"""

from enum import Enum
from typing import Tuple, List, Optional, Any, Dict
from dataclasses import dataclass


class DroneState(Enum):
    """Internal operational state of a drone."""
    IDLE = "IDLE"
    TO_PICKUP = "TO_PICKUP"
    PICKING_UP = "PICKING_UP"
    TO_DESTINATION = "TO_DESTINATION"
    DELIVERING = "DELIVERING"
    TO_CHARGER = "TO_CHARGER"
    CHARGING = "CHARGING"


@dataclass
class DronePerception:
    """Percepts received by the drone agent at each simulation tick."""
    current_pos: Tuple[int, int]
    current_weather: str
    battery_level: float
    detected_obstacles: List[Tuple[int, int]]
    package_status: Optional[str] = None


class DroneAgent:
    """Autonomous drone agent for package delivery and dynamic path execution.

    Attributes:
        drone_id (str): Unique identifier.
        position (Tuple[int, int]): Current (x, y) coordinates.
        battery (float): Current battery charge percentage (0 to 100).
        capacity (float): Maximum battery capacity.
        state (DroneState): Current operational state.
        current_path (List[Tuple[int, int]]): Active planned trajectory.
        assigned_task (Optional[Any]): Current delivery request.
    """

    def __init__(
        self,
        drone_id: str,
        start_pos: Tuple[int, int],
        battery_capacity: float = 100.0,
        low_battery_threshold: float = 25.0,
        move_cost: float = 1.0,
        hover_cost: float = 0.5,
    ):
        """Initialize the drone agent with starting state and configuration."""
        self.drone_id = drone_id
        self.position = start_pos
        self.battery = battery_capacity
        self.battery_capacity = battery_capacity
        self.low_battery_threshold = low_battery_threshold
        self.move_cost = move_cost
        self.hover_cost = hover_cost
        self.state = DroneState.IDLE
        self.current_path: List[Tuple[int, int]] = []
        self.assigned_task: Optional[Any] = None

    def perceive(self, env: Any, weather_str: str) -> DronePerception:
        """Collect sensor percepts from the environment and internal sensors."""
        return DronePerception(
            current_pos=self.position,
            current_weather=weather_str,
            battery_level=self.battery,
            detected_obstacles=list(env.obstacles),
            package_status=self.assigned_task.status if self.assigned_task else None,
        )

    def plan_path(self, destination: Tuple[int, int], env: Any, weather: str) -> List[Tuple[int, int]]:
        """Plan a path from current position to destination using A* search."""
        # Detailed planner integration implemented in Step 3/5
        return []

    def replan_if_needed(self, env: Any, weather: str) -> bool:
        """Check current planned route validity; re-run A* if blocked or cost escalated."""
        # Detailed replanning logic implemented in Step 5
        return False

    def step(self, env: Any, weather_str: str) -> None:
        """Execute one decision and actuation cycle."""
        # Detailed actuation state machine implemented in Step 5
        pass
