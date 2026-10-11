"""sim.delivery_manager

Implements the Delivery Manager Agent.
Coordinates incoming delivery requests and performs task allocation across available drones.
Considers drone distance to package pickup, current battery level, workload, and availability.
Does task allocation only and does not directly control drone flight paths.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class DeliveryRequest:
    """Represents a customer package delivery order."""
    id: str
    pickup: tuple[int, int]
    destination: tuple[int, int]
    deadline_ticks: int
    package_weight: float = 1.0
    status: str = "PENDING"  # PENDING, ASSIGNED, IN_TRANSIT, DELIVERED, EXPIRED
    assigned_drone_id: Optional[str] = None


class DeliveryManagerAgent:
    """Agent that coordinates requests and assigns packages to suitable drones.

    Attributes:
        pending_requests (List[DeliveryRequest]): Unassigned delivery requests.
        completed_requests (List[DeliveryRequest]): Successfully delivered orders.
    """

    def __init__(self, requests: Optional[List[Dict[str, Any]]] = None):
        """Initialize the manager with optional predefined delivery requests."""
        self.pending_requests: List[DeliveryRequest] = []
        self.completed_requests: List[DeliveryRequest] = []
        if requests:
            for req in requests:
                self.add_request(DeliveryRequest(
                    id=req["id"],
                    pickup=tuple(req["pickup"]),
                    destination=tuple(req["destination"]),
                    deadline_ticks=req.get("deadline_ticks", 100),
                    package_weight=req.get("package_weight", 1.0)
                ))

    def add_request(self, request: DeliveryRequest) -> None:
        """Add a new delivery request to the backlog."""
        self.pending_requests.append(request)

    def allocate_requests(self, drones: List[Any]) -> Dict[str, Optional[DeliveryRequest]]:
        """Evaluate suitability scores and assign requests to idle/available drones.

        Suitability criteria:
        - Distance from drone to pickup
        - Current drone battery level
        - Current workload / queue size
        - Drone availability state
        """
        assignments: Dict[str, Optional[DeliveryRequest]] = {}
        # Task allocation logic will be fleshed out in the dedicated step
        return assignments
