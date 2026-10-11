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
from .drone_agent import DroneAgent, create_drone_fleet
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
        self.collision_count = 0
        self.total_collisions_avoided = 0
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
        """Initialize the drone fleet with capacity validation using factory function."""
        valid_count, msg = self.validate_drone_count(count)
        if not valid_count:
            print(f"[Warning] {msg}")

        fleet = create_drone_fleet(count, self.config, self.env)
        self.drones = {d.drone_id: d for d in fleet}

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
        """Advance the entire multi-agent simulation by one tick with collision avoidance."""
        self.current_tick += 1

        # 1. Weather agent updates dynamic conditions
        weather = self.weather_agent.step(env=self.env)
        weather_val = weather.value

        # 2. Delivery manager assigns tasks to available drones
        self.delivery_manager.allocate_requests(
            list(self.drones.values()),
            env=self.env,
            weather_str=weather_val,
            current_tick=self.current_tick,
        )

        # 3. Collision avoidance & coordinated movement reservation
        # Drones prioritized: carrying package > lower battery > drone_id
        drone_list = list(self.drones.values())
        drone_list.sort(key=lambda d: (not d.has_package, d.battery, d.drone_id))

        reserved_cells: Dict[Tuple[int, int], str] = {}
        approved_actions: Dict[str, Any] = {}

        # First pass: Determine intent and resolve conflicts via reservation/hover/replanning
        for drone in drone_list:
            curr_pos = drone.position
            # Perception & initial intention
            perception = drone.perceive(self.env, weather_val)
            target = perception.destination

            # Check if replan needed for environmental changes
            if target is not None:
                drone.check_and_replan_if_needed(target, self.env, weather_val)

            intended_pos = drone.get_intended_next_position()

            # Conflict evaluation
            conflict = False
            # Check A: Cell traversability (obstacle / storm)
            if not self.env.is_traversable(intended_pos, weather=weather_val):
                conflict = True
            # Check B: Cell already reserved by higher-priority drone for this tick
            elif intended_pos in reserved_cells:
                conflict = True
            # Check C: Swap collision (another drone at intended_pos wanting to move to curr_pos)
            else:
                for other in drone_list:
                    if other.drone_id != drone.drone_id and other.position == intended_pos:
                        if other.get_intended_next_position() == curr_pos:
                            conflict = True
                            break

            if conflict and intended_pos != curr_pos and target is not None:
                # Try dynamic replan avoiding reserved cells and conflict cell
                blocked_avoidance = set(reserved_cells.keys()) | {intended_pos}
                replan_ok = drone.handle_dynamic_replanning(
                    target, self.env, weather_val, blocked_cells=blocked_avoidance
                )
                alt_pos = drone.get_intended_next_position()
                if replan_ok and alt_pos != curr_pos and alt_pos not in reserved_cells and self.env.is_traversable(alt_pos, weather=weather_val):
                    # Found clear alternate path!
                    reserved_cells[alt_pos] = drone.drone_id
                    approved_actions[drone.drone_id] = None
                    self.total_collisions_avoided += 1
                else:
                    # No clear alternate move: Hover at current position (Wait rule)
                    reserved_cells[curr_pos] = drone.drone_id
                    from .drone_agent import DroneAction
                    approved_actions[drone.drone_id] = DroneAction.HOVER
                    self.total_collisions_avoided += 1
            elif conflict:
                # Hover at current position
                reserved_cells[curr_pos] = drone.drone_id
                from .drone_agent import DroneAction
                approved_actions[drone.drone_id] = DroneAction.HOVER
                self.total_collisions_avoided += 1
            else:
                # Successfully reserve intended cell
                reserved_cells[intended_pos] = drone.drone_id
                approved_actions[drone.drone_id] = None

        # Second pass: Actuate drones
        for drone in drone_list:
            override_act = approved_actions.get(drone.drone_id)
            prev_completed = len(drone.completed_tasks)
            drone.step(self.env, weather_val, override_action=override_act)

            # Record metrics
            if len(drone.completed_tasks) > prev_completed:
                self.metrics.record_delivery(latency=self.current_tick, success=True)
            self.metrics.record_step(drone.drone_id, distance=1.0, battery_cost=drone.move_cost)

        # 4. Invariant assertion & collision counting (target is strictly 0)
        final_positions = [d.position for d in self.drones.values()]
        shared_cells = len(final_positions) - len(set(final_positions))
        self.collision_count += shared_cells
        self.metrics.total_collisions_avoided = self.total_collisions_avoided
        self.metrics.total_replans_triggered = sum(d.total_replans for d in self.drones.values())

    def run_headless(self, max_ticks: int = 100) -> Dict[str, Any]:
        """Run the simulation without UI for the specified duration."""
        for _ in range(max_ticks):
            self.step()
        return self.metrics.get_summary()
