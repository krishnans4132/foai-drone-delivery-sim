"""sim.environment

Defines the discrete 2D grid environment for the drone delivery simulation.
Models the environment as a graph where cells are nodes and valid moves are edges.
Tracks environmental entities (packages, obstacles, restricted cells, charging stations,
delivery locations, drone start locations).
Provides neighbor calculation with boundary, obstacle, blocked cell, and weather-dependent
restricted cell handling.
Computes per-cell move costs combining base distance, weather multipliers, and restricted-cell penalties.
Supports loading and validation from config.json, including automatic start cell generation when needed.
"""

from enum import Enum
from typing import Tuple, List, Set, Dict, Any, Optional, Union
from dataclasses import dataclass, field
import json
from pathlib import Path


class CellType(Enum):
    """Classification of discrete grid cells."""
    EMPTY = "EMPTY"
    OBSTACLE = "OBSTACLE"
    RESTRICTED = "RESTRICTED"
    CHARGING_STATION = "CHARGING_STATION"
    DELIVERY_LOCATION = "DELIVERY_LOCATION"


@dataclass
class PackageEntity:
    """Environmental package entity waiting for or undergoing delivery."""
    id: str
    pickup: Tuple[int, int]
    destination: Tuple[int, int]
    deadline_ticks: int
    weight: float = 1.0
    status: str = "PENDING"  # PENDING, ASSIGNED, IN_TRANSIT, DELIVERED, EXPIRED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "pickup": list(self.pickup),
            "destination": list(self.destination),
            "deadline_ticks": self.deadline_ticks,
            "weight": self.weight,
            "status": self.status,
        }


@dataclass
class ChargingStationEntity:
    """Environmental charging station entity for battery restoration."""
    position: Tuple[int, int]
    charge_rate: float = 15.0
    occupied_by: Optional[str] = None


class GridEnvironment:
    """Discrete 2D grid environment modeling the physical delivery area.

    Nodes: Valid grid cell coordinates (x, y).
    Edges: Cardinal moves (Up, Down, Left, Right) between adjacent traversable cells.

    Attributes:
        width (int): Grid width in cells.
        height (int): Grid height in cells.
        obstacles (Set[Tuple[int, int]]): Impassable static obstacle coordinates.
        restricted_zones (Set[Tuple[int, int]]): Airspace cells with conditional access (restricted).
        charging_stations (Set[Tuple[int, int]]): Recharging station coordinates.
        start_locations (List[Tuple[int, int]]): Drone starting launch locations.
        packages (Dict[str, PackageEntity]): Environmental packages indexed by ID.
        weather_cost_multipliers (Dict[str, float]): Movement cost multipliers per weather.
    """

    DEFAULT_WEATHER_COSTS = {
        "Clear": 1.0,
        "Windy": 1.5,
        "Rain": 2.0,
        "Storm": 3.0,
    }

    RESTRICTED_SURCHARGE = 1.0  # Extra caution penalty when traversing restricted cells in Clear/Windy

    def __init__(
        self,
        width: int = 20,
        height: int = 20,
        obstacles: Optional[List[Tuple[int, int]]] = None,
        restricted_zones: Optional[List[Tuple[int, int]]] = None,
        charging_stations: Optional[List[Tuple[int, int]]] = None,
        start_locations: Optional[List[Tuple[int, int]]] = None,
        packages: Optional[List[PackageEntity]] = None,
        weather_cost_multipliers: Optional[Dict[str, float]] = None,
    ):
        """Initialize the grid environment with boundaries and entity sets."""
        self.width = width
        self.height = height
        self.obstacles: Set[Tuple[int, int]] = set(obstacles or [])
        self.restricted_zones: Set[Tuple[int, int]] = set(restricted_zones or [])
        self.charging_stations: Set[Tuple[int, int]] = set(charging_stations or [])
        self.start_locations: List[Tuple[int, int]] = list(start_locations or [])
        self.packages: Dict[str, PackageEntity] = {p.id: p for p in (packages or [])}
        self.weather_cost_multipliers: Dict[str, float] = (
            weather_cost_multipliers or dict(self.DEFAULT_WEATHER_COSTS)
        )

    # -------------------------------------------------------------------------
    # Bounds & Traversability
    # -------------------------------------------------------------------------
    def is_within_bounds(self, pos: Tuple[int, int]) -> bool:
        """Check if a coordinate lies within grid boundaries [0, width-1] x [0, height-1]."""
        x, y = pos
        return 0 <= x < self.width and 0 <= y < self.height

    def is_traversable(
        self,
        pos: Tuple[int, int],
        weather: str = "Clear",
        blocked_cells: Optional[Set[Tuple[int, int]]] = None,
    ) -> bool:
        """Determine if a cell is traversable.

        Rules:
        - Out-of-bounds: Impassable.
        - Obstacles: Always impassable.
        - Blocked cells: Impassable (e.g., dynamic storm hazards, temporary closures).
        - Restricted zones:
            - In 'Rain' or 'Storm': Impassable.
            - In 'Clear' or 'Windy': Traversable (with extra path cost).
        """
        if not self.is_within_bounds(pos):
            return False
        if pos in self.obstacles:
            return False
        if blocked_cells and pos in blocked_cells:
            return False
        if weather in ("Rain", "Storm") and pos in self.restricted_zones:
            return False
        return True

    # -------------------------------------------------------------------------
    # Graph Neighbors
    # -------------------------------------------------------------------------
    def neighbors(
        self,
        cell: Tuple[int, int],
        weather: str = "Clear",
        blocked_cells: Optional[Set[Tuple[int, int]]] = None,
    ) -> List[Tuple[int, int]]:
        """Return all valid cardinal 4-connected neighbors (Up, Down, Left, Right).

        Excludes out-of-bounds cells, obstacles, dynamically blocked cells,
        and applies weather-dependent restricted-cell rules.
        """
        x, y = cell
        candidates = [(x, y - 1), (x, y + 1), (x - 1, y), (x + 1, y)]  # Up, Down, Left, Right
        return [
            c for c in candidates
            if self.is_traversable(c, weather=weather, blocked_cells=blocked_cells)
        ]

    def get_neighbors(
        self,
        cell: Tuple[int, int],
        weather: str = "Clear",
        blocked_cells: Optional[Set[Tuple[int, int]]] = None,
    ) -> List[Tuple[int, int]]:
        """Alias for `neighbors` for consistency across codebase."""
        return self.neighbors(cell, weather=weather, blocked_cells=blocked_cells)

    # -------------------------------------------------------------------------
    # Move Cost
    # -------------------------------------------------------------------------
    def get_move_cost(
        self,
        from_cell: Tuple[int, int],
        to_cell: Tuple[int, int],
        weather: str = "Clear",
    ) -> float:
        """Calculate movement cost between two adjacent cells.

        Combines:
        1. Base distance (1.0 for adjacent grid move).
        2. Weather penalty multiplier (Clear: 1.0, Windy: 1.5, Rain: 2.0, Storm: 3.0).
        3. Restricted cell surcharge (+1.0) when traversing a restricted zone in permissible weather.

        Raises:
            ValueError: If target cell is impassable under current conditions.
        """
        if not self.is_traversable(to_cell, weather=weather):
            raise ValueError(f"Cell {to_cell} is impassable under weather '{weather}'.")

        multiplier = self.weather_cost_multipliers.get(weather, 1.0)
        base_cost = 1.0 * multiplier

        # Restricted cell caution surcharge if applicable
        if to_cell in self.restricted_zones:
            base_cost += self.RESTRICTED_SURCHARGE

        return base_cost

    # -------------------------------------------------------------------------
    # Charging Station Helper
    # -------------------------------------------------------------------------
    def get_nearest_charging_station(
        self,
        current_pos: Tuple[int, int],
        weather: str = "Clear",
        require_traversable: bool = False,
    ) -> Optional[Tuple[int, int]]:
        """Find the nearest charging station to current_pos by Manhattan distance.

        Args:
            current_pos: Drone's current (x, y) coordinates.
            weather: Current weather state.
            require_traversable: If True, only considers stations currently traversable.

        Returns:
            The coordinate tuple of the closest station, or None if no stations exist.
        """
        candidates = list(self.charging_stations)
        if require_traversable:
            candidates = [cs for cs in candidates if self.is_traversable(cs, weather)]

        if not candidates:
            return None

        # Sort by Manhattan distance; break ties by coordinate for determinism
        return min(
            candidates,
            key=lambda cs: (abs(cs[0] - current_pos[0]) + abs(cs[1] - current_pos[1]), cs)
        )

    # -------------------------------------------------------------------------
    # Delivery Locations & Packages
    # -------------------------------------------------------------------------
    def get_delivery_destinations(self) -> Set[Tuple[int, int]]:
        """Return the set of all active delivery destinations."""
        return {p.destination for p in self.packages.values() if p.status != "DELIVERED"}

    def add_package(self, package: PackageEntity) -> None:
        """Add an environmental package entity."""
        self.packages[package.id] = package

    # -------------------------------------------------------------------------
    # Fleet Capacity Validation & Start Location Auto-Generation
    # -------------------------------------------------------------------------
    def validate_drone_capacity(self, num_drones: int) -> Tuple[bool, str]:
        """Validate if requested num_drones fits available start and charging cells.

        Returns:
            (is_valid, message)
        """
        if num_drones < 1:
            return False, f"Invalid fleet size ({num_drones}). Must be at least 1."

        available_slots = set(self.start_locations) | self.charging_stations
        available_count = len(available_slots)

        if num_drones > available_count:
            return False, (
                f"Requested {num_drones} drones exceeds available start/charging slots ({available_count}). "
                f"Grid layout currently provides {len(self.start_locations)} start cells and "
                f"{len(self.charging_stations)} charging stations."
            )
        return True, f"Capacity OK: {num_drones} drones fit into {available_count} available slots."

    def ensure_start_locations(
        self,
        num_drones: int,
        auto_generate: bool = True,
    ) -> List[Tuple[int, int]]:
        """Ensure sufficient valid start cells exist for num_drones.

        If start_locations is smaller than num_drones and auto_generate is True,
        generates extra free cells near charging stations or along free grid cells.
        """
        if num_drones < 1:
            raise ValueError(f"Requested num_drones ({num_drones}) must be an integer >= 1.")

        slots: List[Tuple[int, int]] = [
            p for p in self.start_locations
            if self.is_within_bounds(p) and p not in self.obstacles
        ]

        if len(slots) >= num_drones:
            return slots[:num_drones]

        if not auto_generate:
            is_valid, msg = self.validate_drone_capacity(num_drones)
            if not is_valid:
                raise ValueError(msg)
            # Use charging stations as fallback start cells
            for cs in sorted(self.charging_stations):
                if cs not in slots and self.is_traversable(cs):
                    slots.append(cs)
                if len(slots) >= num_drones:
                    return slots[:num_drones]

        # Auto-generation: Search near charging stations, then grid cells
        used = set(slots) | self.obstacles | self.restricted_zones
        candidates: List[Tuple[int, int]] = []

        # 1. First priority: neighbors of charging stations
        for cs in sorted(self.charging_stations):
            for nbr in [(cs[0] + 1, cs[1]), (cs[0] - 1, cs[1]), (cs[0], cs[1] + 1), (cs[0], cs[1] - 1)]:
                if self.is_within_bounds(nbr) and nbr not in used:
                    candidates.append(nbr)
                    used.add(nbr)

        # 2. Second priority: any free cell in the grid
        for y in range(self.height):
            for x in range(self.width):
                pos = (x, y)
                if pos not in used:
                    candidates.append(pos)
                    used.add(pos)

        needed = num_drones - len(slots)
        if len(candidates) < needed:
            raise ValueError(
                f"Grid capacity exhausted: Cannot allocate {num_drones} start positions. "
                f"Available free cells: {len(slots) + len(candidates)}."
            )

        slots.extend(candidates[:needed])
        self.start_locations = list(slots)
        return slots[:num_drones]

    # -------------------------------------------------------------------------
    # Configuration Loading
    # -------------------------------------------------------------------------
    @classmethod
    def from_config(
        cls,
        config: Union[str, Path, Dict[str, Any]],
        requested_drones: Optional[int] = None,
        auto_generate_starts: bool = True,
    ) -> "GridEnvironment":
        """Factory method: Load GridEnvironment directly from config dict or JSON file.

        Validates fleet capacity and automatically provides starting cells.
        """
        if isinstance(config, (str, Path)):
            with open(config, "r") as f:
                cfg = json.load(f)
        else:
            cfg = config

        grid_cfg = cfg.get("grid", {})
        env_cfg = cfg.get("environment", {})
        fleet_cfg = cfg.get("fleet", {})
        weather_cfg = cfg.get("weather", {})
        requests_cfg = cfg.get("delivery_requests", [])

        width = grid_cfg.get("width", 20)
        height = grid_cfg.get("height", 20)
        obstacles = [tuple(p) for p in env_cfg.get("obstacles", [])]
        restricted_zones = [tuple(p) for p in env_cfg.get("restricted_zones", [])]
        charging_stations = [tuple(p) for p in env_cfg.get("charging_stations", [])]
        start_locations = [tuple(p) for p in fleet_cfg.get("start_locations", [])]

        packages = [
            PackageEntity(
                id=r["id"],
                pickup=tuple(r["pickup"]),
                destination=tuple(r["destination"]),
                deadline_ticks=r.get("deadline_ticks", 100),
                weight=r.get("package_weight", 1.0),
                status="PENDING",
            )
            for r in requests_cfg
        ]

        weather_multipliers = weather_cfg.get("cost_multipliers", cls.DEFAULT_WEATHER_COSTS)

        env = cls(
            width=width,
            height=height,
            obstacles=obstacles,
            restricted_zones=restricted_zones,
            charging_stations=charging_stations,
            start_locations=start_locations,
            packages=packages,
            weather_cost_multipliers=weather_multipliers,
        )

        num_drones = requested_drones if requested_drones is not None else fleet_cfg.get("num_drones", 3)
        # Ensure start positions are validated and prepared
        env.ensure_start_locations(num_drones, auto_generate=auto_generate_starts)

        return env

    def to_dict(self) -> Dict[str, Any]:
        """Serialize environment state."""
        return {
            "width": self.width,
            "height": self.height,
            "obstacles": sorted(list(self.obstacles)),
            "restricted_zones": sorted(list(self.restricted_zones)),
            "charging_stations": sorted(list(self.charging_stations)),
            "start_locations": self.start_locations,
            "packages": [p.to_dict() for p in self.packages.values()],
        }
