# Case Study: Simulated Drone Delivery System

## Course Information
- **Course**: Foundations of Artificial Intelligence
- **Course Code**: 23CSE401
- **Academic Year**: 2026–2027

## Team Members
- **CB.SC.U4CSE23603** - ADWAITH RAVEENDRAN
- **CB.SC.U4CSE23628** - KRISHNAN S
- **CB.SC.U4CSE23661** - MADHAV SREEJITH

---

## Overview
Autonomous drones transport packages from source locations to destinations across a 2D grid containing obstacles, restricted areas, charging stations, and dynamic weather conditions. The system features a multi-agent architecture:
1. **Drone Agent**: Primary agent navigating, delivering packages, monitoring battery, and replanning dynamically with A* search.
2. **Delivery Manager Agent**: Coordinates and allocates delivery requests to suitable drones.
3. **Weather Agent**: Stochastic environmental agent introducing Clear, Windy, Rain, and Storm conditions.

## Project Structure
```
drone_delivery_sim/
├── README.md               # Project documentation & team information
├── ASSUMPTIONS.md          # Architectural assumptions and design decisions
├── requirements.txt        # Python package dependencies
├── config.json             # Simulation configuration (grid, fleet, weather, tasks)
├── main.py                 # Primary entry point (interactive UI & headless mode)
├── compare_planners.py     # Comparison benchmarking suite (BFS, DFS, UCS, A*)
├── sim/                    # Decoupled core simulation engine
│   ├── environment.py      # Grid map, obstacles, charging stations, cost evaluation
│   ├── weather_agent.py    # Stochastic weather agent (Clear, Windy, Rain, Storm)
│   ├── delivery_manager.py # Multi-criteria task allocation
│   ├── drone_agent.py      # Drone state machine, battery management, replanning
│   ├── planners.py         # Search algorithms (BFS, DFS, UCS, A*)
│   ├── metrics.py          # PEAS metrics tracking
│   └── simulation.py       # Main simulation coordinator
├── ui/                     # Pygame graphical interface
│   └── renderer.py         # Visualization and live fleet controls
├── tests/                  # Automated pytest test suite
└── results/                # Benchmark outputs and performance logs
```

## Quick Start
```bash
# Install dependencies
pip install -r requirements.txt

# Run interactive simulation with UI
python main.py

# Run with custom drone fleet count
python main.py --drones 5

# Run a specific scenario headlessly
python main.py --scenario stormy_rush --headless

# Compare search planners
python compare_planners.py
```
