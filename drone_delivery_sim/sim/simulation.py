"""sim.simulation

Main coordinator for the Simulated Drone Delivery System.

Tick loop responsibilities:
1. Weather Agent: updates dynamic conditions and injects storm-blocked cells.
2. Delivery Manager Agent: allocates pending requests to eligible drones.
3. Collision avoidance: reservation-based two-pass movement resolution.
4. All Drone Agents: execute one Perceive-Plan-Act cycle per tick.
5. Metrics: record all events (assignments, pickups, deliveries, replans,
   weather changes, collisions) to MetricsTracker / EventLog.

Fleet management API:
- add_drone()    : Dynamically adds a drone at a free start/charging cell.
- remove_drone() : Safely removes a drone; returns its active task to the
                   Delivery Manager queue for reassignment.

Export on completion:
- results/summary.json
- results/summary.csv  (append mode — all runs in one file)
- results/event_log.txt
"""

from typing import Dict, Any, List, Optional, Tuple
import random
from .environment import GridEnvironment
from .weather_agent import WeatherAgent
from .delivery_manager import DeliveryManagerAgent, DeliveryRequest
from .drone_agent import DroneAgent, DroneAction, DroneState, create_drone_fleet
from .metrics import MetricsTracker


class Simulation:
    """Multi-agent simulation coordinator.

    Attributes:
        env (GridEnvironment): Simulated physical space.
        weather_agent (WeatherAgent): Active weather agent.
        delivery_manager (DeliveryManagerAgent): Task allocation agent.
        drones (Dict[str, DroneAgent]): Dynamic fleet of active drones.
        metrics (MetricsTracker): Full performance measurement tracker.
        current_tick (int): Simulation step counter.
        rng (random.Random): Seedable random generator.
        scenario_name (str): Identifier of the active scenario preset.
    """

    def __init__(
        self,
        config: Dict[str, Any],
        drone_override: Optional[int] = None,
        scenario_name: str = "default",
    ):
        """Initialise the simulation from configuration with optional drone override."""
        self.config = config
        self.scenario_name = scenario_name
        self.seed = config.get("seed", 42)
        self.rng = random.Random(self.seed)

        fleet_cfg = config.get("fleet", {})
        target_drones = (
            drone_override if drone_override is not None
            else fleet_cfg.get("num_drones", 3)
        )

        # ---------------------------------------------------------------
        # Environment
        # ---------------------------------------------------------------
        self.env = GridEnvironment.from_config(
            config,
            requested_drones=target_drones,
            auto_generate_starts=True,
        )

        # ---------------------------------------------------------------
        # Weather Agent
        # ---------------------------------------------------------------
        weather_cfg = config.get("weather", {})
        self.weather_agent = WeatherAgent(
            initial_weather=weather_cfg.get("initial_weather", "Clear"),
            transition_matrix=weather_cfg.get("transition_probabilities"),
            cost_multipliers=weather_cfg.get("cost_multipliers"),
            change_interval_ticks=weather_cfg.get("change_interval_ticks", 10),
            rng=random.Random(self.seed + 1),
        )
        self.weather_agent.apply_to_environment(self.env)
        self._last_weather: str = self.weather_agent.current_weather.value

        # ---------------------------------------------------------------
        # Delivery Manager
        # ---------------------------------------------------------------
        self.delivery_manager = DeliveryManagerAgent(
            requests=config.get("delivery_requests", [])
        )

        # ---------------------------------------------------------------
        # Metrics
        # ---------------------------------------------------------------
        self.metrics = MetricsTracker()
        # Register requests for deadline tracking
        all_reqs = list(self.delivery_manager.pending_requests)
        self.metrics.register_requests(all_reqs)

        # ---------------------------------------------------------------
        # State counters
        # ---------------------------------------------------------------
        self.current_tick: int = 0
        self.collision_count: int = 0           # Actual collisions (target: 0)
        self.total_collisions_avoided: int = 0  # Resolved conflicts

        # ---------------------------------------------------------------
        # Drone fleet
        # ---------------------------------------------------------------
        self.drones: Dict[str, DroneAgent] = {}
        self._initialize_fleet(target_drones)

        # Track previous completed-task count per drone to detect new deliveries
        self._prev_completed: Dict[str, int] = {
            did: len(d.completed_tasks) for did, d in self.drones.items()
        }
        # Track previous battery per drone for delta calculation
        self._prev_battery: Dict[str, float] = {
            did: d.battery for did, d in self.drones.items()
        }
        # Track previous distance per drone for delta calculation
        self._prev_distance: Dict[str, float] = {
            did: d.total_distance_moved for did, d in self.drones.items()
        }
        self._replan_log_cursors: Dict[str, int] = {
            did: len(d.replan_event_log) for did, d in self.drones.items()
        }

    # ==================================================================
    # Fleet Management
    # ==================================================================

    def _get_available_start_positions(self) -> List[Tuple[int, int]]:
        """Return free candidate start/charging cells not occupied by any drone."""
        # Expand launch cells the same way initial configuration validation
        # does, so live additions can use remaining free grid / charger cells.
        try:
            self.env.ensure_start_locations(len(self.drones) + 1, auto_generate=True)
        except ValueError:
            return []
        candidates = list(self.env.start_locations)
        for cs in sorted(self.env.charging_stations):
            if cs not in candidates:
                candidates.append(cs)
        occupied = {d.position for d in self.drones.values()}
        return [
            p for p in candidates
            if p not in occupied
            and self.env.is_traversable(p, self.weather_agent.current_weather.value)
        ]

    def _initialize_fleet(self, count: int) -> None:
        """Initialise the drone fleet with capacity validation via the factory function."""
        valid_count, msg = self.validate_drone_count(count)
        if not valid_count:
            print(f"[Warning] {msg}")
        fleet = create_drone_fleet(count, self.config, self.env)
        self.drones = {d.drone_id: d for d in fleet}

    def validate_drone_count(self, requested_count: int) -> Tuple[bool, str]:
        """Validate whether the requested drone count fits the grid start locations."""
        return self.env.validate_drone_capacity(requested_count)

    def add_drone(self) -> bool:
        """Dynamically add one drone to the running simulation.

        Finds a free start/charging cell. Creates and registers the drone.
        Logs the event.

        Returns:
            True if a drone was successfully added; False if no free cell exists.
        """
        free_slots = self._get_available_start_positions()
        if not free_slots:
            return False

        drone_num = len(self.drones) + 1
        drone_id = f"DRONE-{drone_num:02d}"
        while drone_id in self.drones:
            drone_num += 1
            drone_id = f"DRONE-{drone_num:02d}"

        start_pos = free_slots[0]
        fleet_cfg = self.config.get("fleet", {})
        new_drone = DroneAgent(
            drone_id=drone_id,
            start_pos=start_pos,
            battery_capacity=fleet_cfg.get("battery_capacity", 100.0),
            low_battery_threshold=fleet_cfg.get("low_battery_threshold", 25.0),
            charge_rate=fleet_cfg.get("charge_rate_per_tick", 15.0),
            move_cost=fleet_cfg.get("move_energy_cost", 1.0),
            hover_cost=fleet_cfg.get("hover_energy_cost", 0.5),
        )
        self.drones[drone_id] = new_drone
        self._prev_completed[drone_id] = 0
        self._prev_battery[drone_id] = new_drone.battery
        self._prev_distance[drone_id] = 0.0
        self._replan_log_cursors[drone_id] = len(new_drone.replan_event_log)

        self.metrics.record_drone_added(self.current_tick, drone_id, start_pos)
        return True

    def remove_drone(self, drone_id: Optional[str] = None) -> bool:
        """Dynamically remove a drone from the running simulation.

        If the drone is carrying an active task, that task is safely returned
        to the Delivery Manager's pending queue for reassignment.
        Minimum fleet size is 1.

        Args:
            drone_id: ID of drone to remove. If None, removes the last added drone.

        Returns:
            True if removed; False if fleet is already at minimum (1).
        """
        if len(self.drones) <= 1:
            return False

        target_id = drone_id if (drone_id and drone_id in self.drones) \
            else list(self.drones.keys())[-1]

        if target_id not in self.drones:
            return False

        drone = self.drones[target_id]

        # --- Safe task return: requeue active task back to delivery manager ---
        task_requeued = False
        if drone.assigned_task is not None and drone.assigned_task.status != "DELIVERED":
            task = drone.assigned_task
            task.status = "PENDING"
            task.assigned_drone_id = None
            self.delivery_manager.pending_requests.insert(0, task)
            # Remove from assigned list if present
            self.delivery_manager.assigned_requests = [
                r for r in self.delivery_manager.assigned_requests
                if r.id != task.id
            ]
            task_requeued = True

        del self.drones[target_id]
        self._prev_completed.pop(target_id, None)
        self._prev_battery.pop(target_id, None)
        self._prev_distance.pop(target_id, None)
        self._replan_log_cursors.pop(target_id, None)

        self.metrics.record_drone_removed(self.current_tick, target_id, task_requeued)
        return True

    # ==================================================================
    # Core Simulation Tick
    # ==================================================================

    def step(self) -> None:
        """Advance the multi-agent simulation by one tick.

        Sequence:
        1. Weather Agent updates conditions.
        2. Delivery Manager allocates pending requests.
        3. Collision avoidance: reservation-based two-pass movement.
        4. Drone Agents act.
        5. Metrics are recorded.
        """
        self.current_tick += 1
        tick = self.current_tick

        # ------------------------------------------------------------------
        # 1. Weather Agent Step
        # ------------------------------------------------------------------
        weather = self.weather_agent.step(env=self.env)
        weather_val = weather.value

        # Log weather transitions
        if weather_val != self._last_weather:
            self.metrics.record_weather_change(tick, self._last_weather, weather_val)
            self._last_weather = weather_val

        # ------------------------------------------------------------------
        # 2. Delivery Manager: Allocate Requests
        # ------------------------------------------------------------------
        assignment_history_start = len(self.delivery_manager.assignment_history)
        assignments = self.delivery_manager.allocate_requests(
            list(self.drones.values()),
            env=self.env,
            weather_str=weather_val,
            current_tick=tick,
        )

        # Log assignments with score breakdowns
        for event in self.delivery_manager.assignment_history[assignment_history_start:]:
            if event.tick == tick:
                score_str = "; ".join(
                    f"{did}={sb.total_score:.3f}(dist={sb.distance_score:.2f},"
                    f"bat={sb.battery_score:.2f},wl={sb.workload_score:.2f},"
                    f"av={sb.availability_score:.2f})"
                    for did, sb in event.candidate_scores.items()
                )
                self.metrics.record_assignment(
                    tick, event.request_id, event.assigned_drone_id, score_str
                )

        # Log newly expired requests
        for req in self.delivery_manager.expired_requests:
            if getattr(req, "_expiry_logged", False):
                continue
            self.metrics.record_expiry(tick, req.id)
            req._expiry_logged = True  # type: ignore[attr-defined]

        # ------------------------------------------------------------------
        # 3. Collision Avoidance: Priority-Based Reservation
        # Priority: carrying package > lower battery > drone_id (tiebreak)
        # ------------------------------------------------------------------
        drone_list = list(self.drones.values())
        drone_list.sort(key=lambda d: (not d.has_package, d.battery, d.drone_id))

        reserved_cells: Dict[Tuple[int, int], str] = {}
        approved_actions: Dict[str, Any] = {}

        # Pre-seed ALL current positions: every drone holds its cell until it
        # successfully claims a different one. A drone's cell is released from
        # reserved_cells only when it moves away — preventing any other drone
        # from entering a cell that an occupying drone might end up keeping.
        # (Static drones always keep their cell; active drones may release theirs.)
        # CHARGING drones must reach DroneAgent.step() so their battery can
        # increase. They remain stationary through their intended position;
        # treating them as hover-only here bypasses the charging action.
        static_states = (DroneState.DONE, DroneState.IDLE)
        for drone in drone_list:
            reserved_cells[drone.position] = drone.drone_id
            if drone.state in static_states:
                approved_actions[drone.drone_id] = DroneAction.HOVER


        for drone in drone_list:
            # Already handled static drones above
            if drone.state in static_states:
                continue

            curr_pos = drone.position
            if drone.state == DroneState.GOING_TO_CHARGE and drone.active_charger_target:
                reserved_chargers = {
                    other.active_charger_target
                    for other in drone_list
                    if other.drone_id != drone.drone_id
                    and other.state in (DroneState.GOING_TO_CHARGE, DroneState.CHARGING)
                    and other.active_charger_target is not None
                }
                unavailable = set(reserved_cells) | reserved_chargers
                unavailable.discard(curr_pos)
                if drone.active_charger_target in unavailable:
                    free_chargers = [
                        station for station in self.env.charging_stations
                        if station not in unavailable
                        and self.env.is_traversable(station, weather=weather_val)
                    ]
                    if free_chargers:
                        drone.active_charger_target = min(
                            free_chargers,
                            key=lambda station: (
                                abs(station[0] - curr_pos[0]) + abs(station[1] - curr_pos[1]),
                                station,
                            ),
                        )
                        drone.current_path = []
                        drone.plan_path_to(
                            drone.active_charger_target, self.env, weather_val,
                            blocked_cells=unavailable,
                        )

            # Pre-plan path for newly assigned drones (empty path) so that
            # get_intended_next_position() returns the correct first step
            # during conflict resolution rather than the current position.
            if drone.state == DroneState.GOING_TO_PICKUP and not drone.current_path and drone.assigned_task:
                drone.plan_path_to(drone.assigned_task.pickup, self.env, weather_val)
            elif drone.state == DroneState.DELIVERING and not drone.current_path and drone.assigned_task:
                drone.plan_path_to(drone.assigned_task.destination, self.env, weather_val)
            elif drone.state == DroneState.GOING_TO_CHARGE and not drone.current_path and drone.active_charger_target:
                drone.plan_path_to(drone.active_charger_target, self.env, weather_val)

            perception = drone.perceive(self.env, weather_val)
            target = perception.destination

            # Check whether replan is needed before resolving movement
            if target is not None and drone.current_path:
                drone.check_and_replan_if_needed(target, self.env, weather_val)

            intended_pos = drone.get_intended_next_position()

            # Evaluate conflicts
            conflict = False
            conflict_reason = ""

            if not self.env.is_traversable(intended_pos, weather=weather_val):
                conflict = True
                conflict_reason = "impassable_cell"
            # Every drone's current cell is pre-reserved above. Remaining in
            # that cell is legal for this drone (for example, to pick up or
            # deliver a package); only another drone's reservation is a
            # conflict.
            elif (intended_pos in reserved_cells
                  and reserved_cells[intended_pos] != drone.drone_id):
                conflict = True
                conflict_reason = "cell_reserved"
            else:
                # Swap collision: other drone at intended_pos wants curr_pos
                for other in drone_list:
                    if (other.drone_id != drone.drone_id
                            and other.position == intended_pos
                            and other.get_intended_next_position() == curr_pos):
                        conflict = True
                        conflict_reason = "swap_collision"
                        break

            if conflict and intended_pos != curr_pos and target is not None:
                # Try dynamic replan avoiding the reserved cells
                blocked_avoidance = set(reserved_cells.keys()) | {intended_pos}
                # The drone's occupied cell is already reserved for collision
                # checks, but it must remain a traversable A* start node.
                blocked_avoidance.discard(curr_pos)
                replan_ok = drone.handle_dynamic_replanning(
                    target, self.env, weather_val, blocked_cells=blocked_avoidance
                )
                alt_pos = drone.get_intended_next_position()
                if (replan_ok
                        and alt_pos != curr_pos
                        and alt_pos not in reserved_cells
                        and self.env.is_traversable(alt_pos, weather=weather_val)):
                    # Release drone's current cell (it is vacating it)
                    if reserved_cells.get(curr_pos) == drone.drone_id:
                        del reserved_cells[curr_pos]
                    reserved_cells[alt_pos] = drone.drone_id
                    # Store approved next pos so step() is constrained correctly
                    approved_actions[drone.drone_id] = ("MOVE", alt_pos)
                    self.total_collisions_avoided += 1
                    self.metrics.record_collision_avoided(tick, drone.drone_id, "REPLAN")
                else:
                    # Hover at current position (wait rule) — keep cell reserved
                    reserved_cells[curr_pos] = drone.drone_id
                    approved_actions[drone.drone_id] = DroneAction.HOVER
                    self.total_collisions_avoided += 1
                    self.metrics.record_collision_avoided(tick, drone.drone_id, "HOVER")
            elif conflict:
                reserved_cells[curr_pos] = drone.drone_id
                approved_actions[drone.drone_id] = DroneAction.HOVER
                self.total_collisions_avoided += 1
                self.metrics.record_collision_avoided(tick, drone.drone_id, "HOVER")
            else:
                # Drone moves: release its current cell, reserve the target
                if reserved_cells.get(curr_pos) == drone.drone_id and intended_pos != curr_pos:
                    del reserved_cells[curr_pos]
                reserved_cells[intended_pos] = drone.drone_id
                approved_actions[drone.drone_id] = ("MOVE", intended_pos)



        # ------------------------------------------------------------------
        # 4. Actuate Drones + Record Metrics
        # ------------------------------------------------------------------
        for drone in drone_list:
            did = drone.drone_id
            override_act = approved_actions.get(did)

            prev_completed = len(drone.completed_tasks)
            prev_battery = self._prev_battery.get(did, drone.battery)
            prev_distance = self._prev_distance.get(did, drone.total_distance_moved)
            prev_state = drone.state

            # DONE drones have completed all tasks; skip actuation to avoid
            # spurious battery drain and keep them parked at their final position.
            if drone.state == DroneState.DONE:
                action = DroneAction.HOVER
            elif isinstance(override_act, DroneAction):
                # Explicit override (e.g., HOVER due to conflict)
                action = drone.step(self.env, weather_val, override_action=override_act)
            else:
                # ("MOVE", approved_pos) or None: pass reserved cells as blocked
                # so internal replanning inside step() cannot choose a reserved cell.
                approved_pos = override_act[1] if isinstance(override_act, tuple) else None
                other_reserved = {
                    cell for cell, owner in reserved_cells.items()
                    if owner != did and (approved_pos is None or cell != approved_pos)
                }
                other_reserved.update(
                    other.active_charger_target
                    for other in drone_list
                    if other.drone_id != did
                    and other.state in (DroneState.GOING_TO_CHARGE, DroneState.CHARGING)
                    and other.active_charger_target is not None
                )
                action = drone.step(
                    self.env, weather_val,
                    override_action=None,
                    blocked_cells=other_reserved,
                )


            # Distance and battery deltas this tick
            dist_delta = drone.total_distance_moved - prev_distance
            batt_delta = max(0.0, prev_battery - drone.battery)

            is_active = action not in (DroneAction.HOVER, DroneAction.CHARGE) \
                and drone.state not in (DroneState.IDLE, DroneState.DONE)
            is_hovering = action == DroneAction.HOVER

            self.metrics.record_tick_for_drone(
                did,
                distance_delta=dist_delta,
                battery_delta=batt_delta,
                is_active=is_active,
                is_hovering=is_hovering,
            )

            # Detect pickup events
            if (action == DroneAction.PICKUP
                    and drone.assigned_task is not None):
                self.metrics.record_pickup(
                    tick, did,
                    drone.assigned_task.id if drone.assigned_task else "??",
                    drone.position,
                )

            # Detect new deliveries
            new_completed = len(drone.completed_tasks)
            if new_completed > prev_completed:
                completed_task = drone.completed_tasks[-1]
                req_id = getattr(completed_task, "id", "??")
                completed_task.status = "DELIVERED"
                self.delivery_manager.assigned_requests = [
                    request for request in self.delivery_manager.assigned_requests
                    if request.id != req_id
                ]
                if not any(
                    request.id == req_id
                    for request in self.delivery_manager.completed_requests
                ):
                    self.delivery_manager.completed_requests.append(completed_task)
                deadline = self.metrics._request_deadlines.get(req_id, 9999)
                on_time = tick <= deadline
                self.metrics.record_delivery(did, req_id, tick, success=True)
                self.metrics.record_dropoff(tick, did, req_id, drone.position, on_time)

            # Detect charge detours
            if (prev_state != DroneState.GOING_TO_CHARGE
                    and drone.state == DroneState.GOING_TO_CHARGE):
                self.metrics.record_charge_detour(did, tick)

            # Detect new replanning events from drone's log
            new_replans = drone.total_replans - getattr(drone, "_tracked_replans", 0)
            if new_replans > 0:
                cursor = self._replan_log_cursors.get(did, 0)
                new_entries = drone.replan_event_log[cursor:]
                successful_replans = [
                    index for index, entry in enumerate(new_entries)
                    if entry["step"] == "STEP_3_RECOMPUTE_ASTAR"
                    and entry["details"].get("success")
                ]
                last_reason = "route updated"
                for step3_index in successful_replans:
                    step2_index = next(
                        (i for i in range(step3_index - 1, -1, -1)
                         if new_entries[i]["step"] == "STEP_2_CHECK_SUITABILITY"),
                        None,
                    )
                    step1_index = next(
                        (i for i in range(step2_index - 1, -1, -1)
                         if new_entries[i]["step"] == "STEP_1_DETECT_CHANGE"),
                        None,
                    ) if step2_index is not None else None
                    step4_index = next(
                        (i for i in range(step3_index + 1, len(new_entries))
                         if new_entries[i]["step"] == "STEP_4_CONTINUE_ROUTE"),
                        None,
                    )
                    if None in (step1_index, step2_index, step4_index):
                        continue
                    trace = [
                        new_entries[step1_index], new_entries[step2_index],
                        new_entries[step3_index], new_entries[step4_index],
                    ]
                    for entry in trace:
                        self.metrics.event_log.log(
                            tick,
                            "REPLAN_STEP",
                            f"{did}: {entry['step']} | {entry['details']}",
                        )
                    last_reason = new_entries[step3_index]["details"].get(
                        "reason", last_reason
                    )

                self.metrics.record_replan(did, tick, last_reason)
                drone._tracked_replans = drone.total_replans  # type: ignore[attr-defined]
                self._replan_log_cursors[did] = len(drone.replan_event_log)

            # Update delta trackers
            self._prev_battery[did] = drone.battery
            self._prev_distance[did] = drone.total_distance_moved
            self._prev_completed[did] = new_completed

        # ------------------------------------------------------------------
        # 5. Collision Invariant Check (target: 0 actual collisions)
        # ------------------------------------------------------------------
        positions = [d.position for d in self.drones.values()]
        pos_set: Dict[Tuple[int, int], List[str]] = {}
        for drone in self.drones.values():
            pos_set.setdefault(drone.position, []).append(drone.drone_id)

        for cell, drone_ids in pos_set.items():
            if len(drone_ids) > 1:
                self.collision_count += 1
                self.metrics.record_collision(tick, cell, drone_ids)

        # Sync aggregate counters into metrics
        self.metrics.total_collisions = self.collision_count
        self.metrics.total_collisions_avoided = self.total_collisions_avoided
        self.metrics.total_replans_triggered = sum(
            d.total_replans for d in self.drones.values()
        )

    # ==================================================================
    # Headless Runner
    # ==================================================================

    def run_headless(
        self,
        max_ticks: int = 100,
        results_dir: str = "results",
        scenario_name: str = "",
    ) -> Dict[str, Any]:
        """Run the simulation headlessly for up to max_ticks.

        Exports:
        - results/summary.json
        - results/summary.csv  (append mode)
        - results/event_log.txt

        Returns:
            Summary dict from MetricsTracker.get_summary().
        """
        for _ in range(max_ticks):
            self.step()

        summary = self.metrics.get_summary()
        sname = scenario_name or self.scenario_name

        # Export outputs
        json_path = os.path.join(results_dir, "summary.json")
        csv_path = os.path.join(results_dir, "summary.csv")
        log_path = os.path.join(results_dir, "event_log.txt")

        self.metrics.export_summary_json(json_path)
        self.metrics.export_summary_csv(
            csv_path,
            scenario_name=sname,
            fleet_size=len(self.drones),
        )
        self.metrics.export_event_log(log_path)

        return summary


# Local import to avoid circular at module level
import os
