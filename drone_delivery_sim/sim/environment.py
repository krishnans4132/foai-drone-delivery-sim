"""sim.environment

Defines the discrete 2D grid environment for the drone delivery simulation.
Manages cell types (Empty, Obstacle, Restricted, ChargingStation), boundaries,
traversability checks, and base cost calculations under changing environmental conditions.
"""

from enum import Enum
from typing import Tuple, List, Set, Dict, Any


class CellType(Enum):
    """Classification of discrete grid cells."""
    EMPTY = "EMPTY"
    OBSTACLE = "OBSTACLE"
    RESTRICTED = "RESTRICTED"
    CHARGING_STATION = "CHARGING_STATION"


class GridEnvironment:
    """Discrete 2D grid environment modeling the physical delivery area.

    Attributes:
        width (int): Grid width in cells.
        height (int): Grid height in cells.
        obstacles (Set[Tuple[int, int]]): Impassable physical obstacle coordinates.
        restricted_zones (Set[Tuple[int, int]]): Restricted airspace cells (weather-dependent).
        charging_stations (Set[Tuple[int, int]]): Battery recharging station coordinates.
    """

    def __init__(
        self,
        width: int = 20,
        height: int = 20,
        obstacles: List[Tuple[int, int]] = None,
        restricted_zones: List[Tuple[int, int]] = None,
        charging_stations: List[Tuple[int, int]] = None,
    ):
        """Initialize the grid environment with boundaries and special zones."""
        self.width = width
        self.height = height
        self.obstacles: Set[Tuple[int, int]] = set(obstacles or [])
        self.restricted_zones: Set[Tuple[int, int]] = set(restricted_zones or [])
        self.charging_stations: Set[Tuple[int, int]] = set(charging_stations or [])

    def is_within_bounds(self, pos: Tuple[int, int]) -> bool:
        """Check if a coordinate lies within grid boundaries."""
        x, y = pos
        return 0 <= x < self.width and 0 <= y < self.height

    def is_traversable(self, pos: Tuple[int, int], weather: str = "Clear") -> bool:
        """Determine if a cell is traversable under the given weather condition.

        In Rain or Storm, restricted zones become impassable.
        """
        if not self.is_within_bounds(pos):
            return False
        if pos in self.obstacles:
            return False
        if weather in ("Rain", "Storm") and pos in self.restricted_zones:
            return False
        return True

    def get_neighbors(self, pos: Tuple[int, int], weather: str = "Clear") -> List[Tuple[int, int]]:
        """Return valid 4-directional cardinal neighbors (Up, Down, Left, Right)."""
        x, y = pos
        candidates = [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
        return [c for c in candidates if self.is_traversable(c, weather)]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize environment state."""
        return {
            "width": self.width,
            "height": self.height,
            "obstacles": list(self.obstacles),
            "restricted_zones": list(self.restricted_zones),
            "charging_stations": list(self.charging_stations),
        }
