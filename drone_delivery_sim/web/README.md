# Mission Control — React Web Dashboard

Autonomous Drone Delivery Fleet Web Interface built with React 19, Vite, and HTML5 Canvas.

## Overview
This modern web frontend serves as an interactive alternative and companion to the Pygame UI, providing:
- **Interactive 60fps Grid Canvas**: Real-time visualization of drones, flight paths, breadcrumb trails, charging stations, obstacles, restricted zones, and storm cells.
- **Mission Telemetry**: Live fleet cards with battery meters, distance tracking, current tasks, and delivery request status.
- **A* Search Lab**: Click on any two grid cells to run interactive path searches with real-time heuristic value inspection ($f = g + h$), open/closed set visualization, and algorithmic comparison replays against BFS, DFS, and UCS.
- **Decision Explainer**: Real-time explainability panel detailing the Delivery Manager's multi-attribute scoring model and drone replanning reasons.
- **Fleet Benchmark**: Scaling throughput analysis across fleet sizes (1–12 drones).
- **Simulation Controls**: Play/pause, single-tick stepping, speed control (1x to 8x), live weather simulation (Clear, Windy, Rain, Storm), dynamic drone addition/removal, and scenario switching.

## Tech Stack
- **Framework**: React 19 + Vite
- **Styling**: Vanilla CSS (Cyberpunk/Mission Control dark theme, Glassmorphism, CSS tokens)
- **Icons**: Lucide React
- **Rendering**: HTML5 Canvas with sub-pixel interpolation for smooth 60fps drone movement

## Getting Started

### Development Mode (with hot module reload)
```bash
# In drone_delivery_sim/web
npm install
npm run dev
```

### Production Build
```bash
npm run build
```
The compiled static assets are placed in `dist/` and automatically served by Python's Flask server via `python main.py --web` or `python server.py`.

### Linting
```bash
npm run lint
```
