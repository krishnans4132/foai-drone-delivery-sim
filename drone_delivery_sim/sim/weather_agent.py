"""sim.weather_agent

Implements the Weather Agent.
Models stochastic, dynamic environmental condition transitions:
Clear, Windy, Rain, and Storm.
Provides movement cost multipliers and cell traversability constraints for Drone Agents.
"""

from enum import Enum
import random
from typing import Dict, Optional


class WeatherType(Enum):
    """The four weather states specified in the PEAS model."""
    CLEAR = "Clear"
    WINDY = "Windy"
    RAIN = "Rain"
    STORM = "Storm"


class WeatherAgent:
    """Agent responsible for modeling and updating environmental weather conditions.

    Attributes:
        current_weather (WeatherType): Active weather state.
        transition_matrix (Dict[str, Dict[str, float]]): Markov transition probabilities.
        cost_multipliers (Dict[str, float]): Movement/energy cost multiplier per weather type.
        rng (random.Random): Seedable random number generator for reproducibility.
    """

    DEFAULT_COSTS = {
        "Clear": 1.0,
        "Windy": 1.5,
        "Rain": 2.0,
        "Storm": 3.0,
    }

    def __init__(
        self,
        initial_weather: str = "Clear",
        transition_matrix: Optional[Dict[str, Dict[str, float]]] = None,
        cost_multipliers: Optional[Dict[str, float]] = None,
        rng: Optional[random.Random] = None,
    ):
        """Initialize the weather agent with transition rules and an RNG instance."""
        self.current_weather: WeatherType = WeatherType(initial_weather)
        self.transition_matrix = transition_matrix or {}
        self.cost_multipliers = cost_multipliers or self.DEFAULT_COSTS
        self.rng = rng or random.Random(42)

    def step(self) -> WeatherType:
        """Advance weather by one simulation tick based on transition probabilities."""
        curr_name = self.current_weather.value
        transitions = self.transition_matrix.get(curr_name)
        if not transitions:
            return self.current_weather

        states = list(transitions.keys())
        weights = list(transitions.values())
        next_state_name = self.rng.choices(states, weights=weights, k=1)[0]
        self.current_weather = WeatherType(next_state_name)
        return self.current_weather

    def get_cost_multiplier(self) -> float:
        """Return the energy/movement cost multiplier for the current weather."""
        return self.cost_multipliers.get(self.current_weather.value, 1.0)
