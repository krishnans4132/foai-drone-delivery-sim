"""Pygame dashboard for the simulated drone delivery system."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


class UIRenderer:
    """Interactive grid, fleet controls, PEAS summary, and live telemetry."""

    WIDTH = 1680
    HEIGHT = 970
    CELL = 30
    GRID_X = 20
    GRID_Y = 145
    SIDEBAR_X = 650
    SIDEBAR_W = 1010

    BG = (12, 18, 29)
    PANEL = (21, 30, 45)
    PANEL_ALT = (26, 38, 55)
    LINE = (48, 65, 86)
    TEXT = (229, 237, 247)
    MUTED = (151, 168, 190)
    ACCENT = (70, 196, 177)
    DRONE_COLORS = [
        (255, 104, 112), (79, 174, 255), (255, 191, 71), (183, 133, 255),
        (79, 218, 157), (255, 132, 207), (154, 208, 84), (255, 145, 82),
        (89, 221, 218), (220, 226, 104), (140, 159, 255), (242, 110, 78),
    ]
    WEATHER_COLORS = {
        "Clear": (80, 190, 150),
        "Windy": (224, 177, 83),
        "Rain": (78, 150, 226),
        "Storm": (169, 105, 185),
    }
    PLANNERS = ("A*", "BFS", "DFS", "UCS")
    PLANNER_TYPES = {}

    def __init__(
        self,
        sim: Any,
        cell_size: int = 30,
        compact: bool = False,
        base_config: Optional[dict] = None,
        scenario_name: str = "default",
        scenario_applier: Optional[Callable[[dict, str], dict]] = None,
    ):
        self.sim = sim
        self.compact = compact
        if compact:
            self.cell_size = 28
            self.WIDTH = 1480
            self.HEIGHT = 940
            self.GRID_X = 18
            self.GRID_Y = 148
            self.SIDEBAR_X = 610
            self.SIDEBAR_W = 852
        else:
            self.cell_size = cell_size
            self.WIDTH = 1680
            self.HEIGHT = 970
            self.GRID_X = 20
            self.GRID_Y = 145
            self.SIDEBAR_X = self.GRID_X + sim.env.width * self.cell_size + 30
            self.SIDEBAR_W = self.WIDTH - self.SIDEBAR_X - 20

        self.base_config = copy.deepcopy(base_config or sim.config)
        self.scenario_name = scenario_name
        self.scenario_applier = scenario_applier
        self.screen = None
        self.clock = None
        self.title_font = None
        self.font = None
        self.small = None
        self.tiny = None
        self.is_running = False
        self.playing = True
        self.speed = 4
        self.show_routes = True
        self.planner_index = 0
        self.scenarios = list(self.base_config.get("scenarios", {}).keys())
        if not self.scenarios:
            self.scenarios = ["default"]
        if scenario_name not in self.scenarios:
            self.scenarios.insert(0, scenario_name)
        self.scenario_index = self.scenarios.index(scenario_name)
        self.trails: Dict[str, List[Tuple[int, int]]] = {
            did: [drone.position] for did, drone in sim.drones.items()
        }
        self.event_scroll = 0
        self.buttons: List[Tuple[str, Any]] = []
        self.event_panel = None
        self.message = ""
        self.message_until = 0
        self.last_frame_ms = 0
        self.tick_accumulator = 0.0
        self.scenario_override = False
        from ui.extension_panels import ExtensionPanels
        self.extensions = ExtensionPanels(self)
        self.active_extension = "events"
        self.benchmark_rows = []
        self.benchmark_message = "Click Run benchmark to compare the selected scenario."

        from sim.planners import AStarPlanner, BFSPlanner, DFSPlanner, UCSPlanner
        self.PLANNER_TYPES = {
            "A*": AStarPlanner, "BFS": BFSPlanner,
            "DFS": DFSPlanner, "UCS": UCSPlanner,
        }
        # Keep newly added drones on the planner currently selected in the UI.
        self._apply_planner()
        self.extensions.reset_environment()

    def init_display(self) -> None:
        import pygame

        pygame.init()
        self.screen = pygame.display.set_mode((self.WIDTH, self.HEIGHT))
        pygame.display.set_caption(
            "FOAI Drone Delivery System | Foundations of AI (23CSE401)"
        )
        self.clock = pygame.time.Clock()
        if self.compact:
            self.title_font = pygame.font.SysFont("Arial", 18, bold=True)
            self.font = pygame.font.SysFont("Arial", 16)
            self.small = pygame.font.SysFont("Arial", 13)
            self.tiny = pygame.font.SysFont("Arial", 11)
        else:
            self.title_font = pygame.font.SysFont("Arial", 22, bold=True)
            self.font = pygame.font.SysFont("Arial", 18)
            self.small = pygame.font.SysFont("Arial", 15)
            self.tiny = pygame.font.SysFont("Arial", 13)
        self.is_running = True
        self.last_frame_ms = pygame.time.get_ticks()

    def _set_message(self, text: str, seconds: float = 2.8) -> None:
        import pygame

        self.message = text
        self.message_until = pygame.time.get_ticks() + int(seconds * 1000)

    def _apply_planner(self) -> None:
        name = self.PLANNERS[self.planner_index]
        planner_type = self.PLANNER_TYPES[name]
        for drone in self.sim.drones.values():
            drone.planner = planner_type()

    def _rebuild_simulation(self, scenario: Optional[str] = None) -> None:
        from sim.simulation import Simulation

        target = scenario or self.scenarios[self.scenario_index]
        config = copy.deepcopy(self.base_config)
        if target != "default" and self.scenario_applier:
            config = self.scenario_applier(config, target)
        elif target == "default":
            config["_scenario_max_ticks"] = 100
        fleet_size = len(self.sim.drones)
        self.sim = Simulation(config, drone_override=fleet_size, scenario_name=target)
        self.scenario_name = target
        self.scenario_index = self.scenarios.index(target)
        self.trails = {did: [drone.position] for did, drone in self.sim.drones.items()}
        self._apply_planner()
        self.extensions.reset_environment()
        self._set_message(f"Reset: {target.replace('_', ' ').title()} · {fleet_size} drones")

    def _reset(self) -> None:
        self._rebuild_simulation(self.scenario_name)
        self.playing = False

    def _set_weather(self, name: str) -> None:
        previous = self.sim.weather_agent.current_weather.value
        self.sim.weather_agent.set_weather(name, env=self.sim.env)
        self.sim.weather_agent.ticks_since_change = 0
        if previous != name:
            self.sim.metrics.record_weather_change(self.sim.current_tick, previous, name)
        self._set_message(f"Weather forced to {name}")

    def _change_planner(self) -> None:
        self.planner_index = (self.planner_index + 1) % len(self.PLANNERS)
        self._apply_planner()
        self._set_message(f"Planner: {self.PLANNERS[self.planner_index]}")

    def _change_scenario(self) -> None:
        self.scenario_index = (self.scenario_index + 1) % len(self.scenarios)
        self._rebuild_simulation(self.scenarios[self.scenario_index])
        self.playing = False

    def _add_drone(self) -> None:
        next_count = len(self.sim.drones) + 1
        valid, reason = self.sim.validate_drone_count(next_count)
        added = self.sim.add_drone()
        if added:
            self.trails[next(iter(reversed(self.sim.drones)))] = [
                self.sim.drones[next(iter(reversed(self.sim.drones)))].position
            ]
            self._apply_planner()
            self._set_message(f"Drone added · fleet size {len(self.sim.drones)}")
        elif not valid:
            self._set_message(f"Cannot add drone: {reason}")
        else:
            self._set_message(
                "Cannot add drone: no unoccupied start or charging cell is available."
            )

    def _remove_drone(self) -> None:
        if len(self.sim.drones) <= 1:
            self._set_message("At least one drone must remain in the fleet.")
            return
        drone_id = next(reversed(self.sim.drones))
        if self.sim.remove_drone(drone_id):
            self.trails.pop(drone_id, None)
            self._set_message(f"{drone_id} removed · fleet size {len(self.sim.drones)}")
        else:
            self._set_message("Could not remove a drone; the fleet remains unchanged.")

    def _add_random_request(self) -> None:
        from sim.delivery_manager import DeliveryRequest

        occupied = set(self.sim.env.obstacles) | set(self.sim.env.restricted_zones)
        occupied |= set(self.sim.env.charging_stations) | set(self.sim.env.active_storm_blocked_cells)
        occupied |= {drone.position for drone in self.sim.drones.values()}
        free = [
            (x, y)
            for y in range(self.sim.env.height)
            for x in range(self.sim.env.width)
            if (x, y) not in occupied and self.sim.env.is_traversable(
                (x, y), self.sim.weather_agent.current_weather.value
            )
        ]
        if len(free) < 2:
            self._set_message("Cannot add request: not enough free delivery cells.")
            return
        pickup, destination = self.sim.rng.sample(free, 2)
        request_number = self.sim.metrics.total_requests + 1
        request = DeliveryRequest(
            id=f"REQ-LIVE-{request_number:03d}",
            pickup=pickup,
            destination=destination,
            deadline_ticks=self.sim.current_tick + 100,
            package_weight=1.0,
        )
        self.sim.delivery_manager.add_request(request)
        self.sim.metrics.total_requests += 1
        self.sim.metrics._request_deadlines[request.id] = request.deadline_ticks
        self._set_message(f"Added {request.id}: {pickup} → {destination}")

    def _save_screenshot(self) -> None:
        import pygame

        count = len(self.sim.drones)
        target = Path(__file__).resolve().parents[1] / "results" / f"ui_{count}_drones.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        pygame.image.save(self.screen, str(target))
        self._set_message(f"Screenshot saved: {target.name}")

    def _action(self, name: str) -> None:
        if name == "play":
            self.playing = not self.playing
        elif name == "step":
            self.sim.step()
            self._record_trails()
            self.playing = False
        elif name == "slower":
            self.speed = max(1, self.speed - 1)
        elif name == "faster":
            self.speed = min(20, self.speed + 1)
        elif name == "reset":
            self._reset()
        elif name == "scenario":
            self._change_scenario()
        elif name == "planner":
            self._change_planner()
        elif name == "routes":
            self.show_routes = not self.show_routes
        elif name == "add_drone":
            self._add_drone()
        elif name == "remove_drone":
            self._remove_drone()
        elif name == "random_request":
            self._add_random_request()
        elif name.startswith("weather:"):
            self._set_weather(name.split(":", 1)[1])
        elif name == "visualizer":
            self.active_extension = "events" if self.active_extension == "visualizer" else "visualizer"
            self.playing = False
        elif name == "decisions":
            self.active_extension = "events" if self.active_extension == "decisions" else "decisions"
        elif name == "benchmark":
            if self.active_extension == "benchmark":
                self.active_extension = "events"
            else:
                self.active_extension = "benchmark"
                self._run_fleet_benchmark()
        elif name == "events":
            self.active_extension = "events"
        elif name == "search_compare":
            if self.extensions.visualizer.start is None:
                self._set_message("Choose a start and goal on the grid first.")
            else:
                self.extensions.toggle_replay_planner()

    def handle_events(self) -> bool:
        import pygame

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.is_running = False
                return False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    self._action("play")
                elif event.key == pygame.K_RIGHT:
                    self._action("step")
                elif event.key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
                    self._action("add_drone")
                elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                    self._action("remove_drone")
                elif event.key == pygame.K_r:
                    self._action("reset")
                elif event.key == pygame.K_f:
                    self._action("routes")
                elif event.key == pygame.K_p:
                    self._action("planner")
                elif event.key == pygame.K_n:
                    self._action("scenario")
                elif event.key == pygame.K_d:
                    self._action("random_request")
                elif event.key == pygame.K_1:
                    self._action("weather:Clear")
                elif event.key == pygame.K_2:
                    self._action("weather:Windy")
                elif event.key == pygame.K_3:
                    self._action("weather:Rain")
                elif event.key == pygame.K_4:
                    self._action("weather:Storm")
                elif event.key == pygame.K_F12:
                    self._save_screenshot()
                elif event.key == pygame.K_UP:
                    self.event_scroll = min(self.event_scroll + 3, max(0, len(self.sim.metrics.event_log.get_entries()) - 1))
                elif event.key == pygame.K_DOWN:
                    self.event_scroll = max(0, self.event_scroll - 3)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if self.active_extension == "visualizer":
                    gx, gy = event.pos[0] - self.GRID_X, event.pos[1] - self.GRID_Y
                    if 0 <= gx < self.sim.env.width * self.cell_size and 0 <= gy < self.sim.env.height * self.cell_size:
                        self.extensions.pick_grid_cell((gx // self.cell_size, gy // self.cell_size))
                        continue
                for name, rect in self.buttons:
                    if rect.collidepoint(event.pos):
                        self._action(name)
                        break
            elif event.type == pygame.MOUSEWHEEL:
                if self.event_panel and self.event_panel.collidepoint(pygame.mouse.get_pos()):
                    max_scroll = max(0, len(self.sim.metrics.event_log.get_entries()) - 1)
                    self.event_scroll = max(0, min(max_scroll, self.event_scroll + event.y * 3))
        return True

    def _record_trails(self) -> None:
        for drone_id, drone in self.sim.drones.items():
            trail = self.trails.setdefault(drone_id, [])
            if not trail or trail[-1] != drone.position:
                trail.append(drone.position)
                del trail[:-35]
        for drone_id in list(self.trails):
            if drone_id not in self.sim.drones:
                del self.trails[drone_id]

    def _draw_text(self, text: str, x: int, y: int, color=None, font=None) -> None:
        font = font or self.small
        image = font.render(str(text), True, color or self.TEXT)
        self.screen.blit(image, (x, y))

    def _draw_panel(self, rect, title: str, accent=None) -> None:
        import pygame

        pygame.draw.rect(self.screen, self.PANEL, rect, border_radius=10)
        pygame.draw.rect(self.screen, self.LINE, rect, width=1, border_radius=10)
        self._draw_text(title.upper(), rect.x + 12, rect.y + 8, accent or self.ACCENT, self.tiny)

    def _button(self, name: str, label: str, rect, active: bool = False) -> None:
        import pygame

        fill = (42, 61, 82) if active else (30, 45, 63)
        pygame.draw.rect(self.screen, fill, rect, border_radius=7)
        pygame.draw.rect(self.screen, self.ACCENT if active else self.LINE, rect, width=1, border_radius=7)
        image = self.small.render(label, True, self.TEXT)
        self.screen.blit(image, image.get_rect(center=rect.center))
        self.buttons.append((name, rect))

    def _run_fleet_benchmark(self) -> None:
        from benchmark_fleet import run_benchmark
        scenario = self.scenario_name
        max_ticks = int(self.sim.config.get("_scenario_max_ticks", 100))
        out_dir = Path(__file__).resolve().parents[1] / "results"
        self.benchmark_message = "Running independent seeded fleet comparisons…"
        self.benchmark_rows = run_benchmark(
            self.base_config, scenario, [1, 2, 4, 8, 12], self.sim.seed,
            str(out_dir), max_ticks=max_ticks,
        )
        self.benchmark_message = f"Finished · scenario {scenario} · seed {self.sim.seed} · 5 fleet sizes · CSV + SVG saved."

    def _draw_header(self) -> None:
        import pygame

        self.buttons = []
        self._draw_text("FOAI DRONE DELIVERY SYSTEM", self.GRID_X, 10, self.TEXT, self.title_font or self.font)
        self._draw_text("Foundations of AI · 23CSE401", self.GRID_X, 33, self.MUTED, self.small)
        y1 = 55 if not self.compact else 57
        h = 33 if not self.compact else 31
        gap = 7 if not self.compact else 6
        x = self.GRID_X
        controls = [
            ("play", "Pause" if self.playing else "Play", 80 if not self.compact else 75, self.playing),
            ("step", "Step", 65 if not self.compact else 58, False),
            ("slower", "− Slower", 75 if not self.compact else 61, False),
            ("faster", f"Faster + ({self.speed}x)", 115 if not self.compact else 105, False),
            ("reset", "Reset", 70 if not self.compact else 62, False),
            ("scenario", f"Scenario: {self.scenario_name.replace('_', ' ').title()}  ›", 195 if not self.compact else 188, False),
            ("planner", f"Planner: {self.PLANNERS[self.planner_index]}  ›", 135 if not self.compact else 127, False),
            ("routes", f"Routes: {'On' if self.show_routes else 'Off'}", 90 if not self.compact else 82, self.show_routes),
            ("add_drone", f"+ Add drone ({len(self.sim.drones)})", 135 if not self.compact else 125, False),
            ("remove_drone", "− Remove drone", 135 if not self.compact else 125, False),
            ("visualizer", "A* Lab", 80 if not self.compact else 72, self.active_extension == "visualizer"),
            ("decisions", "Why?", 70 if not self.compact else 62, self.active_extension == "decisions"),
            ("benchmark", "Benchmark", 95 if not self.compact else 88, self.active_extension == "benchmark"),
            ("events", "Log", 60 if not self.compact else 52, self.active_extension == "events"),
        ]
        for name, label, width, active in controls:
            rect = pygame.Rect(x, y1, width, h)
            self._button(name, label, rect, active)
            x += width + gap
        x = self.GRID_X
        y2 = 98 if not self.compact else 96
        self._draw_text("FORCE WEATHER", x, y2 + 8, self.MUTED, self.tiny)
        x += 120 if not self.compact else 102
        for weather in ("Clear", "Windy", "Rain", "Storm"):
            width = 82 if not self.compact else 76
            active = weather == self.sim.weather_agent.current_weather.value
            rect = pygame.Rect(x, y2, width, h)
            self._button(f"weather:{weather}", weather, rect, active)
            x += width + gap
        rect = pygame.Rect(x + 2, y2, 160 if not self.compact else 150, h)
        self._button("random_request", "+ Random request", rect)
        keys_x = 730 if not self.compact else 625
        self._draw_text(
            "Keys: Space play/pause · → step · +/- fleet · R reset · 1–4 weather · F routes · P planner · N scenario · D request · F12 screenshot",
            keys_x, y2 + 10, self.MUTED, self.tiny,
        )

    def _draw_grid(self) -> None:
        import pygame

        env = self.sim.env
        size = self.cell_size
        board = pygame.Rect(self.GRID_X, self.GRID_Y, env.width * size, env.height * size)
        pygame.draw.rect(self.screen, (17, 26, 39), board, border_radius=8)
        active_weather = self.sim.weather_agent.current_weather.value
        weather_tint = {
            "Clear": (53, 113, 91), "Windy": (151, 111, 44),
            "Rain": (49, 103, 159), "Storm": (112, 70, 130),
        }[active_weather]

        for y in range(env.height):
            for x in range(env.width):
                cell = (x, y)
                rect = pygame.Rect(self.GRID_X + x * size, self.GRID_Y + y * size, size, size)
                color = (27, 39, 53)
                if cell in env.obstacles:
                    color = (63, 70, 82)
                elif cell in env.restricted_zones:
                    color = (79, 53, 105)
                elif cell in env.charging_stations:
                    color = (25, 74, 87)
                elif active_weather in ("Rain", "Storm") and cell in env.restricted_zones:
                    color = (98, 55, 75)
                pygame.draw.rect(self.screen, color, rect)

                # Low-opacity weather wash keeps map entities and blocked cells clear.
                wash = pygame.Surface((size, size), pygame.SRCALPHA)
                wash.fill((*weather_tint, 20 if active_weather != "Clear" else 8))
                self.screen.blit(wash, rect.topleft)

                if cell in env.obstacles:
                    pygame.draw.line(self.screen, (100, 111, 128), (rect.x + 4, rect.y + size - 4), (rect.x + size - 4, rect.y + 4), 2)
                    pygame.draw.line(self.screen, (100, 111, 128), (rect.x + 4, rect.y + 4), (rect.x + size - 4, rect.y + size - 4), 2)
                elif cell in env.restricted_zones:
                    pygame.draw.line(self.screen, (157, 118, 195), (rect.x + 2, rect.y + size - 3), (rect.x + size - 3, rect.y + 2), 2)
                if cell in env.active_storm_blocked_cells:
                    pygame.draw.rect(self.screen, (185, 62, 77), rect.inflate(-3, -3), border_radius=3)
                    pygame.draw.line(self.screen, (255, 179, 180), rect.topleft, rect.bottomright, 2)
                    pygame.draw.line(self.screen, (255, 179, 180), rect.topright, rect.bottomleft, 2)
                pygame.draw.rect(self.screen, (39, 53, 70), rect, width=1)

        # Routes are behind entity markers.
        if self.show_routes:
            for drone_id, drone in self.sim.drones.items():
                color = self._drone_color(drone_id)
                points = [drone.position] + list(drone.current_path)
                if len(points) > 1:
                    coords = [self._cell_center(p) for p in points]
                    pygame.draw.lines(self.screen, (*color, 120), False, coords, 2)
                    for point in coords[1:]:
                        pygame.draw.circle(self.screen, color, point, 2)

        # Start markers.
        for index, cell in enumerate(env.start_locations):
            if not env.is_within_bounds(cell):
                continue
            cx, cy = self._cell_center(cell)
            pygame.draw.rect(self.screen, (94, 168, 111), (cx - 8, cy - 8, 16, 16), width=1, border_radius=3)
            pygame.draw.circle(self.screen, (129, 203, 139), (cx, cy), 2)

        requests = self._all_requests()
        for request in requests:
            status = getattr(request, "status", "PENDING")
            if status in ("PENDING", "ASSIGNED"):
                cx, cy = self._cell_center(tuple(request.pickup))
                pygame.draw.rect(self.screen, (255, 193, 75), (cx - 7, cy - 7, 14, 14), border_radius=3)
                pygame.draw.rect(self.screen, (255, 235, 177), (cx - 7, cy - 7, 14, 14), width=1, border_radius=3)
            if status != "EXPIRED":
                cx, cy = self._cell_center(tuple(request.destination))
                pygame.draw.circle(self.screen, (83, 219, 151), (cx, cy), 8, 2)
                pygame.draw.line(self.screen, (83, 219, 151), (cx - 4, cy), (cx + 4, cy), 2)
                pygame.draw.line(self.screen, (83, 219, 151), (cx, cy - 4), (cx, cy + 4), 2)

        # Charger glyphs and live drone markers.
        for cell in env.charging_stations:
            cx, cy = self._cell_center(cell)
            pygame.draw.circle(self.screen, (61, 213, 231), (cx, cy), 8)
            pygame.draw.line(self.screen, (12, 47, 58), (cx - 4, cy), (cx + 4, cy), 2)
            pygame.draw.line(self.screen, (12, 47, 58), (cx, cy - 4), (cx, cy + 4), 2)

        for drone_id, drone in self.sim.drones.items():
            color = self._drone_color(drone_id)
            trail = self.trails.get(drone_id, [])
            if len(trail) > 1:
                pygame.draw.lines(self.screen, color, False, [self._cell_center(p) for p in trail], 1)
            cx, cy = self._cell_center(drone.position)
            pygame.draw.circle(self.screen, (10, 18, 27), (cx, cy), 11)
            pygame.draw.circle(self.screen, color, (cx, cy), 9)
            label = drone_id.replace("DRONE-", "")
            image = self.tiny.render(label, True, (9, 16, 23))
            self.screen.blit(image, image.get_rect(center=(cx, cy)))
            bar_w = size - 5
            pygame.draw.rect(self.screen, (18, 22, 29), (cx - bar_w // 2, cy - 14, bar_w, 3), border_radius=2)
            ratio = max(0.0, min(1.0, drone.battery / max(drone.battery_capacity, 1)))
            bat_color = (91, 218, 143) if ratio > .4 else (255, 191, 71) if ratio > .2 else (255, 90, 97)
            pygame.draw.rect(self.screen, bat_color, (cx - bar_w // 2, cy - 14, int(bar_w * ratio), 3), border_radius=2)

        pygame.draw.rect(self.screen, self.LINE, board, width=1, border_radius=8)
        self._draw_legend()
        if self.active_extension == "visualizer":
            self.extensions.draw_grid()

    def _cell_center(self, cell: Tuple[int, int]) -> Tuple[int, int]:
        return (
            self.GRID_X + cell[0] * self.cell_size + self.cell_size // 2,
            self.GRID_Y + cell[1] * self.cell_size + self.cell_size // 2,
        )

    def _drone_color(self, drone_id: str):
        try:
            index = int(drone_id.split("-")[-1]) - 1
        except ValueError:
            index = 0
        return self.DRONE_COLORS[index % len(self.DRONE_COLORS)]

    def _draw_legend(self) -> None:
        import pygame

        y = self.GRID_Y + self.sim.env.height * self.cell_size + 8
        entries = [
            ("Start", (129, 203, 139), "box"), ("Pickup / package", (255, 193, 75), "box"),
            ("Delivery", (83, 219, 151), "ring"), ("Obstacle", (100, 111, 128), "box"),
            ("Restricted", (157, 118, 195), "box"), ("Charger", (61, 213, 231), "dot"),
            ("Storm block", (255, 105, 115), "x"), ("Drone / route / trail", (79, 174, 255), "dot"),
        ]
        col_w = 150 if not self.compact else 142
        for index, (label, color, kind) in enumerate(entries):
            row, col = divmod(index, 4)
            x = self.GRID_X + col * col_w
            yy = y + row * 21
            if kind == "ring":
                pygame.draw.circle(self.screen, color, (x + 7, yy + 7), 6, 2)
            elif kind == "x":
                pygame.draw.line(self.screen, color, (x + 2, yy + 2), (x + 12, yy + 12), 2)
                pygame.draw.line(self.screen, color, (x + 12, yy + 2), (x + 2, yy + 12), 2)
            elif kind == "dot":
                pygame.draw.circle(self.screen, color, (x + 7, yy + 7), 6)
            else:
                pygame.draw.rect(self.screen, color, (x + 2, yy + 2, 11, 11), border_radius=2)
            self._draw_text(label, x + 18, yy, self.MUTED, self.tiny)

    def _all_requests(self) -> List[Any]:
        manager = self.sim.delivery_manager
        requests = {}
        for group in (
            manager.pending_requests, manager.assigned_requests,
            manager.completed_requests, manager.expired_requests,
        ):
            for request in group:
                requests[request.id] = request
        for drone in self.sim.drones.values():
            for request in drone.completed_tasks:
                requests[request.id] = request
            if drone.assigned_task:
                requests[drone.assigned_task.id] = drone.assigned_task
        return list(requests.values())

    def _draw_dashboard(self) -> None:
        import pygame

        x, w = self.SIDEBAR_X, self.SIDEBAR_W
        weather = self.sim.weather_agent.current_weather.value
        weather_color = self.WEATHER_COLORS[weather]

        # Weather + high-level PEAS card.
        self._draw_panel(pygame.Rect(x, 140, w, 72), "Environment / PEAS", weather_color)
        self._draw_text(f"{weather.upper()}  ·  tick {self.sim.current_tick}  ·  seed {self.sim.seed}", x + 14, 163, weather_color, self.font)
        self._draw_text(
            f"P: deliveries / on-time / distance / battery / safety   E: grid + weather   A: move, hover, pickup, deliver, charge   S: pos, route, battery, package, weather",
            x + 14, 191, self.MUTED, self.tiny,
        )

        summary = self.sim.metrics.get_summary()
        ss, fleet, safety, intel = (
            summary["scenario_summary"], summary["fleet"],
            summary["safety"], summary["intelligence"],
        )
        self._draw_panel(pygame.Rect(x, 220, w, 74), "Live performance", self.ACCENT)
        metrics = [
            (f"DELIVERIES  {ss['deliveries_completed']}/{ss['total_requests']}", (83, 219, 151)),
            (f"ON TIME  {ss['deliveries_on_time']}", (113, 206, 167)),
            (f"DISTANCE  {fleet['total_distance_moved']:.0f}", (102, 179, 255)),
            (f"BATTERY  {fleet['total_battery_consumed']:.0f}", (255, 195, 91)),
            (f"UTIL  {fleet['avg_utilisation_pct']:.1f}%", (194, 159, 255)),
            (f"COLLISIONS  {safety['collisions']}", (255, 118, 123)),
            (f"REPLANS  {intel['total_replans']}", (130, 202, 230)),
            (f"FLEET  {len(self.sim.drones)}", self.TEXT),
        ]
        col_w = (w - 28) // 4
        for index, (label, color) in enumerate(metrics):
            col, row = index % 4, index // 4
            self._draw_text(label, x + 14 + col * col_w, 245 + row * 23, color, self.tiny)

        # Per-drone status cards.
        drone_y, drone_h = 302, 182
        self._draw_panel(pygame.Rect(x, drone_y, w, drone_h), "Fleet status", self.ACCENT)
        self._draw_text(
            f"{len(self.sim.drones)} ACTIVE DRONES  ·  add/remove with buttons or +/- keys",
            x + 14, drone_y + 24, self.MUTED, self.tiny,
        )
        rows = list(self.sim.drones.values())[:9]
        bar_x = x + int(w * 0.52)
        bar_w = int(w * 0.16)
        for index, drone in enumerate(rows):
            row_y = drone_y + 45 + index * 14
            color = self._drone_color(drone.drone_id)
            pygame.draw.circle(self.screen, color, (x + 19, row_y + 6), 5)
            carried = drone.assigned_task.id if drone.has_package and drone.assigned_task else "—"
            self._draw_text(drone.drone_id, x + 31, row_y, color, self.tiny)
            self._draw_text(drone.state.value.replace("_", " "), x + 130, row_y, self.TEXT, self.tiny)
            self._draw_text(f"pkg {carried}", x + int(w * 0.28), row_y, self.MUTED, self.tiny)
            self._draw_text(f"{drone.position}", x + int(w * 0.42), row_y, self.MUTED, self.tiny)
            pygame.draw.rect(self.screen, (10, 15, 22), (bar_x, row_y + 2, bar_w, 8), border_radius=4)
            fraction = max(0.0, min(1.0, drone.battery / max(drone.battery_capacity, 1)))
            battery_color = (91, 218, 143) if fraction > .4 else (255, 191, 71) if fraction > .2 else (255, 90, 97)
            pygame.draw.rect(self.screen, battery_color, (bar_x, row_y + 2, int(bar_w * fraction), 8), border_radius=4)
            self._draw_text(f"{drone.battery:.0f}%", bar_x + bar_w + 10, row_y - 1, self.MUTED, self.tiny)
            dist = summary["per_drone"].get(drone.drone_id, {}).get("distance_moved", 0)
            self._draw_text(f"{dist:.0f} cells", x + int(w * 0.82), row_y, self.MUTED, self.tiny)

        # Requests waiting for assignment or delivery.
        queue_y, queue_h = 492, 145
        self._draw_panel(pygame.Rect(x, queue_y, w, queue_h), "Delivery request queue", (255, 194, 93))
        pending = self.sim.delivery_manager.pending_requests
        assigned = self.sim.delivery_manager.assigned_requests
        self._draw_text(f"Waiting {len(pending)}   ·   Assigned / in transit {len(assigned)}", x + 14, queue_y + 24, self.MUTED, self.tiny)
        for index, request in enumerate((pending + assigned)[:5]):
            yy = queue_y + 44 + index * 19
            status = "WAITING" if request in pending else "ASSIGNED"
            color = (255, 198, 99) if status == "WAITING" else (105, 193, 255)
            drone = request.assigned_drone_id or "—"
            self._draw_text(f"{request.id}  {status}", x + 14, yy, color, self.tiny)
            self._draw_text(f"{request.pickup} → {request.destination}", x + int(w * 0.22), yy, self.TEXT, self.tiny)
            self._draw_text(f"due {request.deadline_ticks}", x + int(w * 0.58), yy, self.MUTED, self.tiny)
            self._draw_text(drone, x + int(w * 0.74), yy, self.MUTED, self.tiny)
        if not pending and not assigned:
            self._draw_text("No open requests · use Random request to add one", x + 14, queue_y + 58, self.MUTED, self.small)

        # Optional extension views share the event-log card footprint.
        event_y, event_h = 645, 305
        self.event_panel = pygame.Rect(x, event_y, w, event_h)
        if self.active_extension == "visualizer":
            self.extensions.draw_search_panel(self.event_panel)
            self.extensions.advance()
            return
        if self.active_extension == "decisions":
            self.extensions.draw_decision_panel(self.event_panel)
            return
        if self.active_extension == "benchmark":
            self.extensions.draw_benchmark_panel(self.event_panel)
            return
        self._draw_panel(self.event_panel, "Event log  ·  scroll to browse", (122, 190, 229))
        entries = self.sim.metrics.event_log.get_entries()
        start = max(0, len(entries) - 15 - self.event_scroll)
        visible = entries[start:start + 15]
        if self.event_scroll == 0:
            visible = entries[-15:]
        self.screen.set_clip(pygame.Rect(x + 10, event_y + 27, w - 20, event_h - 34))
        for index, entry in enumerate(visible):
            color = self.MUTED
            for key, value in (
                ("DELIVERY", (113, 223, 165)), ("PICKUP", (255, 200, 91)),
                ("WEATHER", weather_color), ("REPLAN", (183, 153, 255)),
                ("COLLISION", (255, 98, 105)), ("ASSIGNMENT", (129, 194, 241)),
            ):
                if key in entry:
                    color = value
                    break
            self._draw_text(entry[:140], x + 14, event_y + 30 + index * 17, color, self.tiny)
        self.screen.set_clip(None)

    def _draw_about(self) -> None:
        import pygame

        y = self.GRID_Y + self.sim.env.height * self.cell_size + 54
        rect = pygame.Rect(self.GRID_X, y, self.sim.env.width * self.cell_size, self.HEIGHT - y - 18)
        self._draw_panel(rect, "About / controls", self.ACCENT)
        self._draw_text("Case Study: Simulated Drone Delivery System", rect.x + 14, rect.y + 26, self.TEXT, self.small)
        self._draw_text("Foundations of Artificial Intelligence · 23CSE401 · Academic Year 2026–2027", rect.x + 14, rect.y + 46, self.MUTED, self.tiny)
        self._draw_text("CB.SC.U4CSE23603  ADWAITH RAVEENDRAN", rect.x + 14, rect.y + 67, self.TEXT, self.tiny)
        self._draw_text("CB.SC.U4CSE23628  KRISHNAN S", rect.x + 14, rect.y + 85, self.TEXT, self.tiny)
        self._draw_text("CB.SC.U4CSE23661  MADHAV SREEJITH", rect.x + 14, rect.y + 103, self.TEXT, self.tiny)
        self._draw_text("Space play/pause · → step · +/- fleet · R reset · F routes · P planner · N scenario", rect.x + 14, rect.y + 122, self.MUTED, self.tiny)
        self._draw_text("1–4 force weather · D add request · F12 save screenshot", rect.x + 14, rect.y + 137, self.MUTED, self.tiny)

    def render(self) -> None:
        import pygame

        if self.screen is None:
            return
        self._record_trails()
        self.screen.fill(self.BG)
        self._draw_header()
        self._draw_grid()
        self._draw_dashboard()
        self._draw_about()
        now = pygame.time.get_ticks()
        if self.message and now < self.message_until:
            box = pygame.Rect(18, 128, 575, 17)
            pygame.draw.rect(self.screen, (36, 50, 67), box, border_radius=6)
            self._draw_text(self.message[:90], box.x + 10, box.y + 2, (255, 213, 139), self.tiny)
        pygame.display.flip()

    def run_loop(self) -> None:
        import pygame

        self.init_display()
        while self.is_running:
            if not self.handle_events():
                break
            now = pygame.time.get_ticks()
            elapsed = max(0, now - self.last_frame_ms)
            self.last_frame_ms = now
            if self.playing:
                self.tick_accumulator += elapsed * self.speed / 1000.0
                steps = min(8, int(self.tick_accumulator))
                for _ in range(steps):
                    self.sim.step()
                self.tick_accumulator -= steps
            self.render()
            self.clock.tick(30)
        pygame.quit()
