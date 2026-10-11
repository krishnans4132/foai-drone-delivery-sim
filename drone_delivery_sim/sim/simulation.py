"""sim.simulation

Main coordinator for the Simulated Drone Delivery System.
Manages the environment, Weather Agent, Delivery Manager Agent, and the dynamic fleet
of Drone Agents.
Supports headless execution, tick-by-tick simulation stepping, and live dynamic addition/removal
of drones subject to available starting/charging cells.
"""

from typing import Dict, Any, List, Optional, Tuple
import random
from .environment import GridEnvironment
from .weather_agent import WeatherAgent
from .delivery_manager import DeliveryManagerAgent
from .drone_agent import DroneAgent
from .metrics import MetricsTracker


class Simulation:
    """Multi-agent simulation coordinator.

    Attributes:
        env (GridEnvironment): Simulated physical space.
        weather_agent (WeatherAgent): Active weather agent.
        delivery_manager (DeliveryManagerAgent): Task allocation agent.
        drones (Dict[str, DroneAgent]): Dynamic fleet of active drones.
        metrics (MetricsTracker): Operational metrics recorder.
        current_tick (int): Simulation step counter.
        rng (random.Random): Seedable random generator.
    """

    def __init__(self, config: Dict[str, Any], drone_override: Optional[int] = None):
        """Initialize the simulation from configuration with optional drone count override."""
        self.config = config
        self.seed = config.get("seed", 42)
        self.rng = random.Random(self.seed)

        fleet_cfg = config.get("fleet", {})
        target_drones = drone_override if drone_override is not None else fleet_cfg.get("num_drones", 3)
        self.env = GridEnvironment.from_config(
            config,
            requested_drones=target_drones,
            auto_generate_starts=True
        )

        weather_cfg = config.get("weather", {})
        self.weather_agent = WeatherAgent(
            initial_weather=weather_cfg.get("initial_weather", "Clear"),
            transition_matrix=weather_cfg.get("transition_probabilities"),
            cost_multipliers=weather_cfg.get("cost_multipliers"),
            change_interval_ticks=weather_cfg.get("change_interval_ticks", 10),
            rng=random.Random(self.seed + 1),
        )
        self.weather_agent.apply_to_environment(self.env)

        self.delivery_manager = DeliveryManagerAgent(
            requests=config.get("delivery_requests", [])
        )
        self.metrics = MetricsTracker()
        self.current_tick = 0
        self.drones: Dict[str, DroneAgent] = {}

        self._initialize_fleet(target_drones)

    def _get_available_start_positions(self) -> List[Tuple[int, int]]:
        """Return free candidate starting or charging cells not currently occupied by drones."""
        candidates = list(self.env.start_locations)
        for cs in sorted(self.env.charging_stations):
            if cs not in candidates:
                candidates.append(cs)

        occupied = {d.position for d in self.drones.values()}
        free_slots = [
            p for p in candidates
            if p not in occupied and self.env.is_traversable(p, self.weather_agent.current_weather.value)
        ]
        return free_slots

    def _initialize_fleet(self, count: int) -> None:
        """Initialize the drone fleet with capacity validation."""
        valid_count, msg = self.validate_drone_count(count)
        if not valid_count:
            print(f"[Warning] {msg}")

        for i in range(1, count + 1):
            success = self.add_drone()
            if not success:
                print(f"[Warning] Could only spawn {len(self.drones)} of {count} requested drones.")
                break

    def validate_drone_count(self, requested_count: int) -> Tuple[bool, str]:
        """Validate if requested drone count can fit into the grid and start locations."""
        return self.env.validate_drone_capacity(requested_count)

    def add_drone(self) -> bool:
        """Dynamically add one drone to the running simulation.

        Returns True if successful, False if no free cell was available.
        """
        free_slots = self._get_available_start_positions()
        if not free_slots:
            return False

        drone_num = len(self.drones) + 1
        drone_id = f"DRONE-{drone_num:02d}"
        # Ensure unique ID
        while drone_id in self.drones:
            drone_num += 1
            drone_id = f"DRONE-{drone_num:02d}"

        start_pos = free_slots[0]
        fleet_cfg = self.config.get("fleet", {})
        self.drones[drone_id] = DroneAgent(
            drone_id=drone_id,
            start_pos=start_pos,
            battery_capacity=fleet_cfg.get("battery_capacity", 100.0),
            low_battery_threshold=fleet_cfg.get("low_battery_threshold", 25.0),
            move_cost=fleet_cfg.get("move_energy_cost", 1.0),
            hover_cost=fleet_cfg.get("hover_energy_cost", 0.5),
        )
        return True

    def remove_drone(self, drone_id: Optional[str] = None) -> bool:
        """Dynamically remove a drone (by ID or latest added).

        Returns True if a drone was removed, False if fleet is already at minimum (1).
        """
        if len(self.drones) <= 1:
            return False  # Minimum 1 drone required by ground rules

        target_id = drone_id if drone_id else list(self.drones.keys())[-1]
        if target_id in self.drones:
            del self.drones[target_id]
            return True
        return False

    def step(self) -> None:
        """Advance the entire multi-agent simulation by one tick."""
        self.current_tick += 1
        # 1. Weather agent updates dynamic conditions
        weather = self.weather_agent.step(env=self.env)

        # 2. Delivery manager assigns tasks to available drones
        self.delivery_manager.allocate_requests(list(self.drones.values()))

        # 3. Each drone perceives, plans, acts
        for drone in list(self.drones.values()):
            drone.step(self.env, weather.value)

    def run_headless(self, max_ticks: int = 100) -> Dict[str, Any]:
        """Run the simulation without UI for the specified duration."""
        for _ in range(max_ticks):
            self.step()
        return self.metrics.get_summary()
