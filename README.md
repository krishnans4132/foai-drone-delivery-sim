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
Autonomous drones transport packages from source locations to destinations across a 2D grid containing obstacles, restricted areas, charging stations, and dynamic weather conditions. The problem is modeled as a state-space search problem with A* Search for route planning and dynamic replanning for environmental changes.

### Multi-Agent Architecture
1. **Drone Agent**: Primary agent. Navigates, monitors battery, avoids obstacles, recharges at charging stations, and delivers packages.
2. **Delivery Manager Agent**: Coordinates incoming delivery requests and allocates them to suitable drones based on distance, battery, workload, and availability.
3. **Weather Agent**: Stochastic agent introducing changing weather conditions (Clear, Windy, Rain, Storm).

---

## Project Structure
```
.
├── SPEC.md                 # Complete project specification & PEAS model
├── ASSUMPTIONS.md          # Architectural assumptions and design decisions
├── FOAI_CaseStudy.pdf      # University case study brief
├── drone_delivery_sim/     # Source code
│   ├── config.json         # Simulation configuration & scenarios
│   ├── main.py             # Main entry point (CLI and GUI)
│   ├── compare_planners.py # Benchmark suite (BFS, DFS, UCS, A*)
│   ├── sim/                # Core decoupled simulation engine
│   ├── ui/                 # Pygame interface
│   ├── tests/              # Pytest test suite
│   └── results/            # Benchmark outputs and metric logs
```

## Quick Start
```bash
# Navigate to simulation directory
cd drone_delivery_sim

# Install dependencies
pip install -r requirements.txt

# Run interactive simulation with UI
python main.py

# Run with custom drone fleet count
python main.py --drones 5

# Run headlessly
python main.py --headless --ticks 100

# Run automated tests
pytest tests/
```
