"""sim.metrics

Tracks PEAS performance measures for the Simulated Drone Delivery System:
- Delivery success and timeliness
- Total travel distance and step count
- Energy and battery efficiency
- Collision avoidance records
- Fleet utilization and workload sharing
"""

from typing import Dict, Any, List
from dataclasses import dataclass, field


@dataclass
class MetricsTracker:
    """Collects and reports operational metrics across simulation runs."""
    total_deliveries_completed: int = 0
    total_deliveries_failed: int = 0
    total_travel_distance: float = 0.0
    total_battery_consumed: float = 0.0
    total_replans_triggered: int = 0
    total_collisions_avoided: int = 0
    drone_step_counts: Dict[str, int] = field(default_factory=dict)
    delivery_latencies: List[int] = field(default_factory=list)

    def record_delivery(self, latency: int, success: bool = True) -> None:
        """Record outcome of a delivery order."""
        if success:
            self.total_deliveries_completed += 1
            self.delivery_latencies.append(latency)
        else:
            self.total_deliveries_failed += 1

    def record_step(self, drone_id: str, distance: float = 1.0, battery_cost: float = 1.0) -> None:
        """Record drone movement step and energy expenditure."""
        self.drone_step_counts[drone_id] = self.drone_step_counts.get(drone_id, 0) + 1
        self.total_travel_distance += distance
        self.total_battery_consumed += battery_cost

    def get_summary(self) -> Dict[str, Any]:
        """Generate high-level PEAS summary metrics."""
        avg_latency = (
            sum(self.delivery_latencies) / len(self.delivery_latencies)
            if self.delivery_latencies else 0.0
        )
        return {
            "deliveries_completed": self.total_deliveries_completed,
            "deliveries_failed": self.total_deliveries_failed,
            "average_delivery_latency": avg_latency,
            "total_travel_distance": self.total_travel_distance,
            "total_battery_consumed": self.total_battery_consumed,
            "total_replans": self.total_replans_triggered,
            "fleet_size": len(self.drone_step_counts),
        }
