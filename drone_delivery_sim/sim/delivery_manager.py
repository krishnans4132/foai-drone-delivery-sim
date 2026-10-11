"""sim.delivery_manager

Implements the Delivery Manager Agent.
Coordinates incoming delivery requests and performs multi-attribute task allocation across the drone fleet.
Considers:
1. Distance to package pickup (lower is better)
2. Current battery level (higher is better)
3. Current workload (fewer prior deliveries is better, promoting workload sharing)
4. Drone availability state (idle drones preferred)

Configurable factor weights allow tuning allocation policy.
Skips unavailable drones and drones whose current battery cannot cover pickup + delivery + detour to charger.
Records detailed per-drone score breakdowns for transparency, logging, and the UI.
Strict architectural decoupling: The manager only assigns tasks; it has NO movement methods and never alters drone positions.
Works seamlessly for any fleet size, including 1.
"""

from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass, field
import copy

from .planners import manhattan_distance


@dataclass
class DeliveryRequest:
    """Represents a customer package delivery order with deadline and status."""
    id: str
    pickup: Tuple[int, int]
    destination: Tuple[int, int]
    deadline_ticks: int
    package_weight: float = 1.0
    weight: float = 1.0
    status: str = "PENDING"  # PENDING, ASSIGNED, IN_TRANSIT, DELIVERED, EXPIRED
    assigned_drone_id: Optional[str] = None

    def __post_init__(self):
        # Synchronize weight aliases
        if self.weight != 1.0 and self.package_weight == 1.0:
            self.package_weight = self.weight
        elif self.package_weight != 1.0 and self.weight == 1.0:
            self.weight = self.package_weight


@dataclass
class ScoreBreakdown:
    """Detailed score breakdown for a drone candidate on a specific delivery request."""
    drone_id: str
    raw_distance: float
    distance_score: float
    battery_score: float
    workload_score: float
    availability_score: float
    total_score: float
    is_eligible: bool
    disqualification_reason: Optional[str] = None


@dataclass
class AssignmentEvent:
    """Audit log entry capturing task allocation decision and candidate evaluations."""
    tick: int
    request_id: str
    assigned_drone_id: Optional[str]
    candidate_scores: Dict[str, ScoreBreakdown]


class DeliveryManagerAgent:
    """Delivery Manager Agent responsible for queue management and task allocation.

    Attributes:
        pending_requests (List[DeliveryRequest]): Backlog of pending delivery orders.
        assigned_requests (List[DeliveryRequest]): Requests currently being handled by drones.
        completed_requests (List[DeliveryRequest]): Successfully delivered orders.
        expired_requests (List[DeliveryRequest]): Orders that expired before assignment/delivery.
        weights (Dict[str, float]): Weights for distance, battery, workload, and availability.
        assignment_history (List[AssignmentEvent]): Historical log of task allocation events.
    """

    DEFAULT_WEIGHTS = {
        "distance": 0.35,
        "battery": 0.25,
        "workload": 0.25,
        "availability": 0.15,
    }

    def __init__(
        self,
        requests: Optional[List[Dict[str, Any]]] = None,
        weights: Optional[Dict[str, float]] = None,
        max_grid_dimension: int = 40,
        max_workload_ref: int = 10,
    ):
        """Initialize the manager with optional predefined requests and scoring weights."""
        self.pending_requests: List[DeliveryRequest] = []
        self.assigned_requests: List[DeliveryRequest] = []
        self.completed_requests: List[DeliveryRequest] = []
        self.expired_requests: List[DeliveryRequest] = []

        self.weights = dict(self.DEFAULT_WEIGHTS)
        if weights:
            self.weights.update(weights)

        self.max_grid_dimension = max(1, max_grid_dimension)
        self.max_workload_ref = max(1, max_workload_ref)
        self.assignment_history: List[AssignmentEvent] = []

        if requests:
            for req in requests:
                self.add_request(DeliveryRequest(
                    id=req["id"],
                    pickup=tuple(req["pickup"]),
                    destination=tuple(req["destination"]),
                    deadline_ticks=req.get("deadline_ticks", 100),
                    package_weight=req.get("package_weight", 1.0),
                    weight=req.get("package_weight", 1.0),
                ))

    def add_request(self, request: DeliveryRequest) -> None:
        """Add a new delivery request to the pending queue."""
        self.pending_requests.append(request)

    def get_queue_size(self) -> int:
        """Return the number of unassigned pending delivery requests."""
        return len(self.pending_requests)

    # -------------------------------------------------------------------------
    # Scoring Model
    # -------------------------------------------------------------------------
    def score_drone_for_request(
        self,
        drone: Any,
        request: DeliveryRequest,
        env: Optional[Any] = None,
        weather_str: str = "Clear",
    ) -> ScoreBreakdown:
        """Calculate the suitability score of a single drone for a delivery request.

        Factors:
        1. Distance score: Closer to pickup yields higher score (0 to 1).
        2. Battery score: Higher battery percentage yields higher score (0 to 1).
        3. Workload score: Fewer past/current tasks yields higher score (0 to 1).
        4. Availability score: IDLE state = 1.0, otherwise 0.0.

        Checks eligibility:
        - Must be in IDLE state (available).
        - Battery must cover pickup + delivery + detour to charger.
        """
        drone_pos = drone.position
        dist = manhattan_distance(drone_pos, request.pickup)

        # 1. Distance score: 1.0 when dist == 0, scaling to 0.0 at max_grid_dimension
        dist_score = max(0.0, 1.0 - (dist / self.max_grid_dimension))

        # 2. Battery score: percentage in [0.0, 1.0]
        battery_pct = max(0.0, min(1.0, drone.battery / drone.battery_capacity))
        batt_score = battery_pct

        # 3. Workload score: completed tasks + active task count
        active_load = 1 if getattr(drone, "assigned_task", None) is not None else 0
        completed_count = len(getattr(drone, "completed_tasks", []))
        total_load = completed_count + active_load
        workload_score = max(0.0, 1.0 - (total_load / self.max_workload_ref))

        # 4. Availability score
        state_val = getattr(drone.state, "value", str(drone.state))
        is_idle = (state_val == "IDLE") and (getattr(drone, "assigned_task", None) is None)
        avail_score = 1.0 if is_idle else 0.0

        # Eligibility check
        is_eligible = True
        disqualify_reason = None

        if not is_idle:
            is_eligible = False
            disqualify_reason = f"Drone is not IDLE (state: {state_val})"

        # Energy reachability check
        if is_eligible and env is not None:
            mult = getattr(env, "weather_cost_multipliers", {}).get(weather_str, 1.0)
            delivery_dist = manhattan_distance(request.pickup, request.destination)
            nearest_cs = env.get_nearest_charging_station(request.destination, weather=weather_str)
            cs_dist = manhattan_distance(request.destination, nearest_cs) if nearest_cs else 0

            # Required energy: drone to pickup + pickup to dest + dest to charger
            required_energy = (dist + delivery_dist + cs_dist) * getattr(drone, "move_cost", 1.0) * mult
            if drone.battery < required_energy:
                is_eligible = False
                disqualify_reason = (
                    f"Insufficient battery ({drone.battery:.1f} < {required_energy:.1f} required for route + charger detour)"
                )

        # Compute weighted total score
        w = self.weights
        total_score = (
            w["distance"] * dist_score +
            w["battery"] * batt_score +
            w["workload"] * workload_score +
            w["availability"] * avail_score
        )

        return ScoreBreakdown(
            drone_id=drone.drone_id,
            raw_distance=dist,
            distance_score=round(dist_score, 4),
            battery_score=round(batt_score, 4),
            workload_score=round(workload_score, 4),
            availability_score=round(avail_score, 4),
            total_score=round(total_score, 4),
            is_eligible=is_eligible,
            disqualification_reason=disqualify_reason,
        )

    # -------------------------------------------------------------------------
    # Task Allocation Loop
    # -------------------------------------------------------------------------
    def allocate_requests(
        self,
        drones: List[Any],
        env: Optional[Any] = None,
        weather_str: str = "Clear",
        current_tick: int = 0,
    ) -> Dict[str, Optional[DeliveryRequest]]:
        """Coordinate and allocate pending delivery orders to suitable available drones.

        Evaluates pending requests (sorted by deadline). For each request, scores all drones.
        Assigns the request to the eligible drone with the highest suitability score.
        Strictly does NOT move any drones.

        Returns:
            Dict mapping drone_id to newly assigned DeliveryRequest (or None).
        """
        new_assignments: Dict[str, Optional[DeliveryRequest]] = {}

        if not drones or not self.pending_requests:
            return new_assignments

        # Check and process expired requests
        active_pending: List[DeliveryRequest] = []
        for req in self.pending_requests:
            if current_tick > req.deadline_ticks and req.status == "PENDING":
                req.status = "EXPIRED"
                self.expired_requests.append(req)
            else:
                active_pending.append(req)
        self.pending_requests = active_pending

        # Sort pending queue by deadline (earliest deadline first)
        self.pending_requests.sort(key=lambda r: r.deadline_ticks)

        remaining_pending: List[DeliveryRequest] = []
        assigned_drones_this_cycle: Set[str] = set()

        for request in self.pending_requests:
            candidate_scores: Dict[str, ScoreBreakdown] = {}
            best_drone = None
            best_score = -1.0

            for drone in drones:
                # If already assigned a task in this cycle, skip
                if drone.drone_id in assigned_drones_this_cycle:
                    breakdown = self.score_drone_for_request(drone, request, env, weather_str)
                    breakdown.is_eligible = False
                    breakdown.disqualification_reason = "Already assigned another order in current tick"
                    candidate_scores[drone.drone_id] = breakdown
                    continue

                breakdown = self.score_drone_for_request(drone, request, env, weather_str)
                candidate_scores[drone.drone_id] = breakdown

                if breakdown.is_eligible and breakdown.total_score > best_score:
                    best_score = breakdown.total_score
                    best_drone = drone

            # Record decision event for logging and UI telemetry
            event = AssignmentEvent(
                tick=current_tick,
                request_id=request.id,
                assigned_drone_id=best_drone.drone_id if best_drone else None,
                candidate_scores=candidate_scores,
            )
            self.assignment_history.append(event)

            if best_drone is not None:
                request.status = "ASSIGNED"
                request.assigned_drone_id = best_drone.drone_id
                best_drone.assign_task(request)
                assigned_drones_this_cycle.add(best_drone.drone_id)
                self.assigned_requests.append(request)
                new_assignments[best_drone.drone_id] = request
            else:
                remaining_pending.append(request)

        self.pending_requests = remaining_pending
        return new_assignments

    def get_latest_breakdown(self) -> Optional[AssignmentEvent]:
        """Return the most recent task allocation event breakdown."""
        return self.assignment_history[-1] if self.assignment_history else None

    def get_assignment_history(self) -> List[AssignmentEvent]:
        """Return full history of assignment events."""
        return list(self.assignment_history)
