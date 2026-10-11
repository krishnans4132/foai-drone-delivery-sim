"""sim.weather_agent

Implements the Weather Agent.
Models stochastic, dynamic environmental condition transitions across exactly four states:
- Clear: normal movement cost (1.0x).
- Windy: increased movement/energy cost (1.5x).
- Rain: higher movement cost (2.0x) and restricted cells become impassable.
- Storm: maximum movement cost (3.0x), restricted cells impassable, and selected routes/cells
         become temporarily unavailable (storm-blocked cells).

Characteristics:
- Stochastic, seedable changes using a configurable Markov transition table applied every N ticks.
- Directly applies effects to the environment (cost multipliers, storm-blocked cells).
- Exposes only current weather state and current environmental impact (Partially Observable).
  Never exposes or computes a future schedule.
- Provides a manual override method for UI interactivity and deterministic scenario testing.
"""

from enum import Enum
import random
from typing import Dict, Set, Tuple, Optional, Any, Union, List


class WeatherType(Enum):
    """The four weather states specified in the FOAI Case Study PEAS model."""
    CLEAR = "Clear"
    WINDY = "Windy"
    RAIN = "Rain"
    STORM = "Storm"


class WeatherAgent:
    """Agent responsible for stochastic weather transitions and environmental impacts.

    Attributes:
        current_weather (WeatherType): Currently active environmental weather state.
        transition_matrix (Dict[str, Dict[str, float]]): Markov transition probabilities.
        cost_multipliers (Dict[str, float]): Movement/energy cost multiplier per weather type.
        change_interval_ticks (int): Number of ticks between stochastic weather evaluation.
        ticks_since_change (int): Ticks elapsed since the last weather update.
        storm_blocked_cells (Set[Tuple[int, int]]): Cells temporarily impassable during Storm.
        storm_cells_count (int): Default number of cells blocked when entering Storm.
        rng (random.Random): Seedable RNG instance guaranteeing reproducible transitions.
    """

    DEFAULT_TRANSITIONS = {
        "Clear": {"Clear": 0.70, "Windy": 0.20, "Rain": 0.08, "Storm": 0.02},
        "Windy": {"Clear": 0.30, "Windy": 0.50, "Rain": 0.15, "Storm": 0.05},
        "Rain":  {"Clear": 0.15, "Windy": 0.25, "Rain": 0.50, "Storm": 0.10},
        "Storm": {"Clear": 0.10, "Windy": 0.30, "Rain": 0.40, "Storm": 0.20},
    }

    DEFAULT_COSTS = {
        "Clear": 1.0,
        "Windy": 1.5,
        "Rain": 2.0,
        "Storm": 3.0,
    }

    def __init__(
        self,
        initial_weather: Union[WeatherType, str] = WeatherType.CLEAR,
        transition_matrix: Optional[Dict[str, Dict[str, float]]] = None,
        cost_multipliers: Optional[Dict[str, float]] = None,
        change_interval_ticks: int = 10,
        storm_cells_count: int = 5,
        rng: Optional[random.Random] = None,
        seed: Optional[int] = None,
    ):
        """Initialize the weather agent with transition matrix, update interval, and RNG."""
        if isinstance(initial_weather, str):
            self.current_weather = WeatherType(initial_weather)
        else:
            self.current_weather = initial_weather

        self.transition_matrix = transition_matrix or dict(self.DEFAULT_TRANSITIONS)
        self.cost_multipliers = cost_multipliers or dict(self.DEFAULT_COSTS)
        self.change_interval_ticks = max(1, change_interval_ticks)
        self.ticks_since_change = 0
        self.storm_cells_count = storm_cells_count
        self.storm_blocked_cells: Set[Tuple[int, int]] = set()

        if rng is not None:
            self.rng = rng
        elif seed is not None:
            self.rng = random.Random(seed)
        else:
            self.rng = random.Random(42)

    # -------------------------------------------------------------------------
    # Perception / Observation (Partially Observable Interface)
    # -------------------------------------------------------------------------
    @property
    def weather(self) -> WeatherType:
        """Expose current weather for drones to perceive.

        Strictly returns current state; never exposes a future schedule.
        """
        return self.current_weather

    def get_cost_multiplier(self) -> float:
        """Return the energy/movement cost multiplier for the current weather."""
        return self.cost_multipliers.get(self.current_weather.value, 1.0)

    def get_storm_blocked_cells(self) -> Set[Tuple[int, int]]:
        """Return a copy of currently storm-blocked cells."""
        return set(self.storm_blocked_cells)

    # -------------------------------------------------------------------------
    # Simulation Step & Markov Transition
    # -------------------------------------------------------------------------
    def step(self, env: Optional[Any] = None) -> WeatherType:
        """Advance the weather agent by one simulation tick.

        Evaluates Markov state transitions every `change_interval_ticks`.
        Applies effects to `env` if provided.

        Returns:
            The active WeatherType for the tick.
        """
        self.ticks_since_change += 1

        if self.ticks_since_change >= self.change_interval_ticks:
            self._execute_transition(env)
            self.ticks_since_change = 0

        if env is not None:
            self.apply_to_environment(env)

        return self.current_weather

    def _execute_transition(self, env: Optional[Any] = None) -> None:
        """Perform stochastic Markov state transition using configured probabilities."""
        curr_name = self.current_weather.value
        transitions = self.transition_matrix.get(curr_name, self.DEFAULT_TRANSITIONS.get(curr_name, {}))

        if not transitions:
            return

        states = list(transitions.keys())
        weights = list(transitions.values())
        next_state_name = self.rng.choices(states, weights=weights, k=1)[0]
        next_weather = WeatherType(next_state_name)

        if next_weather == WeatherType.STORM:
            # Entering or continuing storm: update/generate storm-blocked cells
            self.storm_blocked_cells = self._generate_storm_blocked_cells(env)
        else:
            # Clear storm-blocked cells when weather is not Storm
            self.storm_blocked_cells.clear()

        self.current_weather = next_weather

    def _generate_storm_blocked_cells(self, env: Optional[Any] = None) -> Set[Tuple[int, int]]:
        """Deterministically generate storm-blocked cells/corridors using seedable RNG.

        Selects traversable cells, preserving charging stations and avoiding static obstacles.
        """
        blocked: Set[Tuple[int, int]] = set()

        if env is not None and hasattr(env, "width") and hasattr(env, "height"):
            # Sample candidate cells that are not obstacles or charging stations
            candidates: List[Tuple[int, int]] = []
            for y in range(env.height):
                for x in range(env.width):
                    pos = (x, y)
                    if (
                        pos not in env.obstacles
                        and pos not in env.charging_stations
                        and pos not in getattr(env, "start_locations", [])
                    ):
                        candidates.append(pos)

            if candidates:
                k = min(self.storm_cells_count, len(candidates))
                # Sort first so RNG sample is deterministic across Python runs
                candidates.sort()
                blocked = set(self.rng.sample(candidates, k))
        else:
            # Fallback deterministic cell generation when no env reference is provided
            for _ in range(self.storm_cells_count):
                x = self.rng.randint(0, 19)
                y = self.rng.randint(0, 19)
                blocked.add((x, y))

        return blocked

    # -------------------------------------------------------------------------
    # Environmental Effects Application
    # -------------------------------------------------------------------------
    def apply_to_environment(self, env: Any) -> None:
        """Directly apply weather effects to the GridEnvironment.

        Updates active storm-blocked cells and weather cost multipliers.
        """
        if hasattr(env, "active_storm_blocked_cells"):
            env.active_storm_blocked_cells = set(self.storm_blocked_cells)

        if hasattr(env, "weather_cost_multipliers"):
            env.weather_cost_multipliers = dict(self.cost_multipliers)

    # -------------------------------------------------------------------------
    # Manual Override (For UI Controls & Scenario Testing)
    # -------------------------------------------------------------------------
    def set_weather(
        self,
        weather: Union[WeatherType, str],
        storm_blocked_cells: Optional[Set[Tuple[int, int]]] = None,
        env: Optional[Any] = None,
    ) -> WeatherType:
        """Manually override the current weather state.

        Used by UI hotkeys/buttons and scenario configurations.
        Resets `ticks_since_change` to 0 so override persists for at least one interval.
        """
        if isinstance(weather, str):
            self.current_weather = WeatherType(weather)
        else:
            self.current_weather = weather

        if self.current_weather == WeatherType.STORM:
            if storm_blocked_cells is not None:
                self.storm_blocked_cells = set(storm_blocked_cells)
            else:
                self.storm_blocked_cells = self._generate_storm_blocked_cells(env)
        else:
            self.storm_blocked_cells.clear()

        self.ticks_since_change = 0

        if env is not None:
            self.apply_to_environment(env)

        return self.current_weather
