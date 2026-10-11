"""sim.metrics

Full performance measurement and event logging for the Simulated Drone Delivery System.

Tracks:
- Deliveries completed vs total requests, and on-time deliveries.
- Per-drone and total distance moved.
- Per-drone and total battery consumed.
- Collision count (target: 0) and collisions avoided.
- Replan events (count and summary).
- Drone utilisation (fraction of ticks each drone was actively moving/picking/delivering).
- Exports: results/summary.json, results/summary.csv, results/event_log.txt
"""

import csv
import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Event Log Entry
# ---------------------------------------------------------------------------

class EventLog:
    """Structured event log that records all significant simulation events.

    Events are stored in memory and can be flushed to results/event_log.txt.
    Each entry is a human-readable line with a tick stamp and category tag.
    """

    def __init__(self) -> None:
        self._entries: List[str] = []

    def log(self, tick: int, category: str, message: str) -> None:
        """Append a log entry."""
        entry = f"[T{tick:04d}] [{category:<18s}] {message}"
        self._entries.append(entry)

    def get_entries(self) -> List[str]:
        """Return all log entries."""
        return list(self._entries)

    def flush_to_file(self, path: str) -> None:
        """Write all entries to the specified file path."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for entry in self._entries:
                f.write(entry + "\n")

    def clear(self) -> None:
        """Clear all entries."""
        self._entries.clear()


# ---------------------------------------------------------------------------
# Per-Drone Statistics
# ---------------------------------------------------------------------------

@dataclass
class DroneStats:
    """Accumulated performance statistics for a single drone agent."""
    drone_id: str
    ticks_active: int = 0          # Ticks the drone was not idle/hovering
    ticks_total: int = 0           # All ticks the drone participated in
    distance_moved: float = 0.0    # Grid cells traversed
    battery_consumed: float = 0.0  # Energy units consumed
    deliveries_completed: int = 0  # Packages successfully delivered
    deliveries_on_time: int = 0    # Deliveries completed before deadline
    replans_triggered: int = 0     # Route replanning events
    charge_detours: int = 0        # Low-battery detours to charging station
    hovering_ticks: int = 0        # Ticks spent hovering/waiting


# ---------------------------------------------------------------------------
# MetricsTracker
# ---------------------------------------------------------------------------

@dataclass
class MetricsTracker:
    """Collects and reports operational metrics across the full simulation run.

    Attributes:
        total_requests:          Total delivery requests in the scenario.
        total_deliveries_completed: Successfully delivered packages.
        total_deliveries_on_time:   Deliveries within their deadline.
        total_deliveries_failed:    Requests expired or undeliverable.
        total_travel_distance:   Cumulative distance all drones moved.
        total_battery_consumed:  Cumulative battery energy consumed.
        total_replans_triggered: Total route replan events across all drones.
        total_collisions:        Cell-sharing collisions (target: 0).
        total_collisions_avoided: Conflicts resolved by hover/replan.
        per_drone (Dict):        Per-drone DroneStats keyed by drone_id.
        event_log (EventLog):    Full structured event log.
    """
    total_requests: int = 0
    total_deliveries_completed: int = 0
    total_deliveries_on_time: int = 0
    total_deliveries_failed: int = 0
    total_travel_distance: float = 0.0
    total_battery_consumed: float = 0.0
    total_replans_triggered: int = 0
    total_collisions: int = 0
    total_collisions_avoided: int = 0

    per_drone: Dict[str, DroneStats] = field(default_factory=dict)
    event_log: EventLog = field(default_factory=EventLog)

    # Internal: delivery deadlines for on-time tracking
    _request_deadlines: Dict[str, int] = field(default_factory=dict)

    def register_requests(self, requests: List[Any]) -> None:
        """Register all delivery requests for deadline tracking."""
        for req in requests:
            req_id = getattr(req, "id", None) or req.get("id", "UNKNOWN")
            deadline = getattr(req, "deadline_ticks", None) or req.get("deadline_ticks", 9999)
            self._request_deadlines[req_id] = deadline
        self.total_requests = len(requests)

    def _ensure_drone(self, drone_id: str) -> DroneStats:
        """Lazily initialise per-drone stats entry."""
        if drone_id not in self.per_drone:
            self.per_drone[drone_id] = DroneStats(drone_id=drone_id)
        return self.per_drone[drone_id]

    # ------------------------------------------------------------------
    # Recording methods (called from Simulation.step)
    # ------------------------------------------------------------------

    def record_tick_for_drone(
        self,
        drone_id: str,
        distance_delta: float,
        battery_delta: float,
        is_active: bool,
        is_hovering: bool,
    ) -> None:
        """Record per-drone stats for one simulation tick."""
        stats = self._ensure_drone(drone_id)
        stats.ticks_total += 1
        if is_active:
            stats.ticks_active += 1
        if is_hovering:
            stats.hovering_ticks += 1
        stats.distance_moved += distance_delta
        stats.battery_consumed += battery_delta

        self.total_travel_distance += distance_delta
        self.total_battery_consumed += battery_delta

    def record_delivery(
        self,
        drone_id: str,
        request_id: str,
        tick: int,
        success: bool = True,
    ) -> None:
        """Record a delivery outcome (success or failure/expiry)."""
        stats = self._ensure_drone(drone_id)
        if success:
            self.total_deliveries_completed += 1
            stats.deliveries_completed += 1
            deadline = self._request_deadlines.get(request_id, 9999)
            if tick <= deadline:
                self.total_deliveries_on_time += 1
                stats.deliveries_on_time += 1
        else:
            self.total_deliveries_failed += 1

    def record_replan(self, drone_id: str, tick: int, reason: str) -> None:
        """Record a dynamic replanning event."""
        stats = self._ensure_drone(drone_id)
        stats.replans_triggered += 1
        self.total_replans_triggered += 1
        self.event_log.log(tick, "REPLAN", f"{drone_id}: {reason}")

    def record_charge_detour(self, drone_id: str, tick: int) -> None:
        """Record a low-battery charging detour."""
        stats = self._ensure_drone(drone_id)
        stats.charge_detours += 1
        self.event_log.log(tick, "CHARGE_DETOUR", f"{drone_id} diverting to nearest charging station")

    def record_collision(self, tick: int, cell: Any, drone_ids: List[str]) -> None:
        """Record a cell-sharing collision (should remain 0)."""
        self.total_collisions += 1
        self.event_log.log(tick, "COLLISION", f"Cell {cell} shared by {drone_ids}")

    def record_collision_avoided(self, tick: int, drone_id: str, action: str) -> None:
        """Record a conflict resolution (hover/replan prevented collision)."""
        self.total_collisions_avoided += 1
        self.event_log.log(tick, "CONFLICT_AVOIDED", f"{drone_id} resolved via {action}")

    def record_weather_change(self, tick: int, old_weather: str, new_weather: str) -> None:
        """Record a weather state transition."""
        self.event_log.log(
            tick, "WEATHER_CHANGE",
            f"{old_weather} -> {new_weather}"
        )

    def record_assignment(
        self,
        tick: int,
        request_id: str,
        drone_id: Optional[str],
        score_breakdown: Optional[str] = None,
    ) -> None:
        """Record a task assignment event with optional score breakdown."""
        if drone_id:
            msg = f"Request {request_id} assigned to {drone_id}"
            if score_breakdown:
                msg += f" | Scores: {score_breakdown}"
        else:
            msg = f"Request {request_id} could NOT be assigned (no eligible drone)"
        self.event_log.log(tick, "ASSIGNMENT", msg)

    def record_pickup(self, tick: int, drone_id: str, request_id: str, cell: Any) -> None:
        """Record a package pickup event."""
        self.event_log.log(tick, "PICKUP", f"{drone_id} picked up {request_id} at {cell}")

    def record_dropoff(self, tick: int, drone_id: str, request_id: str, cell: Any, on_time: bool) -> None:
        """Record a successful package delivery event."""
        status = "ON TIME" if on_time else "LATE"
        self.event_log.log(
            tick, "DELIVERY",
            f"{drone_id} delivered {request_id} at {cell} [{status}]"
        )

    def record_expiry(self, tick: int, request_id: str) -> None:
        """Record a delivery request expiry due to missed deadline."""
        self.total_deliveries_failed += 1
        self.event_log.log(tick, "EXPIRY", f"Request {request_id} expired (deadline missed)")

    def record_drone_added(self, tick: int, drone_id: str, pos: Any) -> None:
        """Record dynamic addition of a drone to the fleet."""
        self.event_log.log(tick, "FLEET_ADD", f"{drone_id} added to fleet at {pos}")

    def record_drone_removed(self, tick: int, drone_id: str, task_requeued: bool) -> None:
        """Record dynamic removal of a drone from the fleet."""
        requeue_note = " (task returned to queue)" if task_requeued else ""
        self.event_log.log(tick, "FLEET_REMOVE", f"{drone_id} removed from fleet{requeue_note}")

    # ------------------------------------------------------------------
    # Summary Generation
    # ------------------------------------------------------------------

    def get_summary(self) -> Dict[str, Any]:
        """Generate comprehensive PEAS performance summary."""
        total = self.total_requests if self.total_requests > 0 else 1
        completed = self.total_deliveries_completed

        fleet_size = len(self.per_drone)
        total_ticks = max((s.ticks_total for s in self.per_drone.values()), default=1)

        # Utilisation: average fraction of ticks each drone was actively working
        if self.per_drone:
            utilisation_pct = (
                sum(s.ticks_active / max(s.ticks_total, 1) for s in self.per_drone.values())
                / fleet_size * 100
            )
        else:
            utilisation_pct = 0.0

        per_drone_summary = {}
        for did, s in sorted(self.per_drone.items()):
            per_drone_summary[did] = {
                "deliveries_completed": s.deliveries_completed,
                "deliveries_on_time": s.deliveries_on_time,
                "distance_moved": round(s.distance_moved, 2),
                "battery_consumed": round(s.battery_consumed, 2),
                "replans_triggered": s.replans_triggered,
                "charge_detours": s.charge_detours,
                "utilisation_pct": round(
                    s.ticks_active / max(s.ticks_total, 1) * 100, 1
                ),
                "hovering_ticks": s.hovering_ticks,
            }

        return {
            "scenario_summary": {
                "total_requests": self.total_requests,
                "deliveries_completed": completed,
                "deliveries_on_time": self.total_deliveries_on_time,
                "deliveries_failed_or_expired": self.total_deliveries_failed,
                "completion_rate_pct": round(completed / total * 100, 1),
                "on_time_rate_pct": round(
                    self.total_deliveries_on_time / max(completed, 1) * 100, 1
                ),
            },
            "fleet": {
                "fleet_size": fleet_size,
                "avg_utilisation_pct": round(utilisation_pct, 1),
                "total_distance_moved": round(self.total_travel_distance, 2),
                "total_battery_consumed": round(self.total_battery_consumed, 2),
                "avg_distance_per_drone": round(
                    self.total_travel_distance / max(fleet_size, 1), 2
                ),
                "avg_battery_per_drone": round(
                    self.total_battery_consumed / max(fleet_size, 1), 2
                ),
            },
            "safety": {
                "collisions": self.total_collisions,
                "conflicts_resolved": self.total_collisions_avoided,
            },
            "intelligence": {
                "total_replans": self.total_replans_triggered,
            },
            "per_drone": per_drone_summary,
        }

    # ------------------------------------------------------------------
    # Export Methods
    # ------------------------------------------------------------------

    def export_summary_json(self, path: str) -> None:
        """Write summary metrics to a JSON file."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        summary = self.get_summary()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)

    def export_summary_csv(self, path: str, scenario_name: str = "", fleet_size: int = 0) -> None:
        """Write flat summary metrics to a CSV file (append-friendly for multi-run comparisons)."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        summary = self.get_summary()
        ss = summary["scenario_summary"]
        fl = summary["fleet"]
        sf = summary["safety"]
        intel = summary["intelligence"]

        row = {
            "scenario": scenario_name,
            "fleet_size": fleet_size or fl["fleet_size"],
            "total_requests": ss["total_requests"],
            "deliveries_completed": ss["deliveries_completed"],
            "deliveries_on_time": ss["deliveries_on_time"],
            "deliveries_failed": ss["deliveries_failed_or_expired"],
            "completion_rate_pct": ss["completion_rate_pct"],
            "on_time_rate_pct": ss["on_time_rate_pct"],
            "total_distance": fl["total_distance_moved"],
            "total_battery": fl["total_battery_consumed"],
            "avg_utilisation_pct": fl["avg_utilisation_pct"],
            "collisions": sf["collisions"],
            "conflicts_resolved": sf["conflicts_resolved"],
            "total_replans": intel["total_replans"],
        }

        write_header = not os.path.exists(path) or os.path.getsize(path) == 0
        with open(path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(row.keys()))
            if write_header:
                writer.writeheader()
            writer.writerow(row)

    def export_event_log(self, path: str) -> None:
        """Write the full event log to a text file."""
        self.event_log.flush_to_file(path)
