"""tests.test_weather_agent

Unit tests for sim/weather_agent.py:
- Verification of the 4 exact weather conditions (Clear, Windy, Rain, Storm)
- Weather effect application on the environment:
  - Clear: base cost (1.0x), traversable restricted cells, no storm cells
  - Windy: increased cost (1.5x)
  - Rain: high cost (2.0x), restricted cells impassable
  - Storm: highest cost (3.0x), restricted cells impassable, dynamic storm-blocked cells
- Manual override (set_weather)
- Stochastic transitions every N ticks
- Seedable RNG reproducibility
- Partial observability check (no future schedule exposure)
"""

import random
import pytest
from sim.environment import GridEnvironment
from sim.weather_agent import WeatherAgent, WeatherType


def test_weather_types_enumeration():
    """Verify exactly four weather conditions exist as specified in the PEAS model."""
    expected = {"Clear", "Windy", "Rain", "Storm"}
    actual = {w.value for w in WeatherType}
    assert actual == expected
    assert len(WeatherType) == 4


def test_weather_effects_clear():
    """Verify Clear condition has 1.0x cost multiplier and no storm blocked cells."""
    env = GridEnvironment(width=10, height=10, restricted_zones=[(2, 2)])
    agent = WeatherAgent(initial_weather="Clear")
    agent.apply_to_environment(env)

    assert agent.current_weather == WeatherType.CLEAR
    assert agent.get_cost_multiplier() == 1.0
    assert len(agent.get_storm_blocked_cells()) == 0
    assert env.is_traversable((2, 2), weather="Clear")
    assert env.get_move_cost((2, 1), (2, 2), weather="Clear") == 2.0  # 1.0 base + 1.0 restricted surcharge


def test_weather_effects_windy():
    """Verify Windy condition increases cost multiplier to 1.5x."""
    env = GridEnvironment(width=10, height=10, restricted_zones=[(2, 2)])
    agent = WeatherAgent(initial_weather="Windy")
    agent.apply_to_environment(env)

    assert agent.current_weather == WeatherType.WINDY
    assert agent.get_cost_multiplier() == 1.5
    assert env.is_traversable((2, 2), weather="Windy")
    assert env.get_move_cost((2, 1), (2, 2), weather="Windy") == 2.5  # 1.5 base + 1.0 restricted surcharge


def test_weather_effects_rain():
    """Verify Rain condition increases cost to 2.0x and makes restricted cells impassable."""
    env = GridEnvironment(width=10, height=10, restricted_zones=[(2, 2)])
    agent = WeatherAgent(initial_weather="Rain")
    agent.apply_to_environment(env)

    assert agent.current_weather == WeatherType.RAIN
    assert agent.get_cost_multiplier() == 2.0
    # Restricted cells are impassable in Rain
    assert not env.is_traversable((2, 2), weather="Rain")
    with pytest.raises(ValueError):
        env.get_move_cost((2, 1), (2, 2), weather="Rain")


def test_weather_effects_storm():
    """Verify Storm condition has 3.0x cost, impassable restricted cells, and storm-blocked cells."""
    env = GridEnvironment(width=10, height=10, restricted_zones=[(2, 2)])
    agent = WeatherAgent(initial_weather="Clear", storm_cells_count=3, seed=99)
    # Trigger Storm override with auto-generated storm cells
    agent.set_weather("Storm", env=env)

    assert agent.current_weather == WeatherType.STORM
    assert agent.get_cost_multiplier() == 3.0
    assert not env.is_traversable((2, 2), weather="Storm")

    # Storm blocked cells must be active on both agent and environment
    storm_cells = agent.get_storm_blocked_cells()
    assert len(storm_cells) == 3
    assert env.active_storm_blocked_cells == storm_cells

    # All storm blocked cells must be impassable
    for sc in storm_cells:
        assert not env.is_traversable(sc, weather="Storm")
        assert sc not in env.neighbors((sc[0] + 1, sc[1]), weather="Storm")


def test_manual_override_set_weather():
    """Verify set_weather immediately overrides state and updates environment."""
    env = GridEnvironment(width=10, height=10)
    agent = WeatherAgent(initial_weather="Clear", seed=42)

    # Override to Windy
    agent.set_weather("Windy", env=env)
    assert agent.current_weather == WeatherType.WINDY
    assert agent.get_cost_multiplier() == 1.5

    # Override to Storm with specific custom blocked cells
    custom_storm_cells = {(3, 3), (4, 4)}
    agent.set_weather(WeatherType.STORM, storm_blocked_cells=custom_storm_cells, env=env)
    assert agent.current_weather == WeatherType.STORM
    assert env.active_storm_blocked_cells == custom_storm_cells

    # Override back to Clear clears storm cells
    agent.set_weather("Clear", env=env)
    assert agent.current_weather == WeatherType.CLEAR
    assert len(env.active_storm_blocked_cells) == 0


def test_markov_transition_every_n_ticks():
    """Verify transitions occur every N ticks and not on intermediate ticks."""
    env = GridEnvironment(width=10, height=10)
    interval = 5
    # Force transitions to always switch to Windy from Clear
    deterministic_matrix = {
        "Clear": {"Windy": 1.0},
        "Windy": {"Rain": 1.0},
        "Rain": {"Storm": 1.0},
        "Storm": {"Clear": 1.0},
    }
    agent = WeatherAgent(
        initial_weather="Clear",
        transition_matrix=deterministic_matrix,
        change_interval_ticks=interval,
        seed=1,
    )

    # Ticks 1 to 4: Weather must remain Clear
    for tick in range(1, interval):
        res = agent.step(env=env)
        assert res == WeatherType.CLEAR
        assert agent.current_weather == WeatherType.CLEAR

    # Tick 5: Weather transitions to Windy
    res5 = agent.step(env=env)
    assert res5 == WeatherType.WINDY
    assert agent.current_weather == WeatherType.WINDY


def test_reproducibility_with_fixed_seed():
    """Verify two independent agents with the same seed produce identical trajectories."""
    env1 = GridEnvironment(width=10, height=10)
    env2 = GridEnvironment(width=10, height=10)

    agent1 = WeatherAgent(initial_weather="Clear", change_interval_ticks=3, seed=777)
    agent2 = WeatherAgent(initial_weather="Clear", change_interval_ticks=3, seed=777)

    trajectory1 = []
    trajectory2 = []
    storm_cells1 = []
    storm_cells2 = []

    for _ in range(50):
        w1 = agent1.step(env=env1)
        w2 = agent2.step(env=env2)
        trajectory1.append(w1)
        trajectory2.append(w2)
        storm_cells1.append(sorted(list(agent1.get_storm_blocked_cells())))
        storm_cells2.append(sorted(list(agent2.get_storm_blocked_cells())))

    assert trajectory1 == trajectory2
    assert storm_cells1 == storm_cells2


def test_partial_observability_no_future_schedule():
    """Verify the agent does not expose any precomputed future schedule."""
    agent = WeatherAgent(initial_weather="Clear")
    assert not hasattr(agent, "future_schedule")
    assert not hasattr(agent, "future_weather")
    assert not hasattr(agent, "peek_next")
    assert not hasattr(agent, "weather_queue")
    # Only current weather is observable
    assert hasattr(agent, "weather")
    assert hasattr(agent, "current_weather")
