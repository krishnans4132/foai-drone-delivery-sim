"""Separate dashboard panels for optional, observational extensions."""

from __future__ import annotations


class ExtensionPanels:
    def __init__(self, renderer):
        self.ui = renderer
        from sim.search_visualizer import AStarSearchVisualizer, DecisionExplainer
        self.AStarSearchVisualizer = AStarSearchVisualizer
        self.explainer = DecisionExplainer()
        self.visualizer = AStarSearchVisualizer(renderer.sim.env, renderer.sim.weather_agent.current_weather.value)
        self.replay_planner = "BFS"
        self.replay_result = None
        self.query_pick = None

    def reset_environment(self):
        self.visualizer = self.AStarSearchVisualizer(
            self.ui.sim.env, self.ui.sim.weather_agent.current_weather.value
        )
        self.replay_result = None
        self.query_pick = None

    def pick_grid_cell(self, cell):
        if self.query_pick is None:
            self.query_pick = cell
            self.ui._set_message(f"A* visualizer start: {cell}; click a goal cell")
            return
        self.visualizer.start_search(self.query_pick, cell, self.ui.sim.weather_agent.current_weather.value)
        self.query_pick = None
        self.replay_result = None
        self.ui._set_message(f"A* query: {self.visualizer.start} → {self.visualizer.goal}")

    def advance(self):
        if self.visualizer.start is not None and not self.visualizer.done:
            self.visualizer.step()

    def toggle_replay_planner(self):
        self.replay_planner = {"BFS": "DFS", "DFS": "UCS", "UCS": "BFS"}[self.replay_planner]
        if self.visualizer.start is not None:
            self.replay_result = self.visualizer.replay(self.replay_planner)

    def draw_grid(self):
        import pygame
        ui, visualizer = self.ui, self.visualizer
        for cell in visualizer.open_set:
            pygame.draw.rect(ui.screen, (30, 135, 123), self._cell_rect(cell), border_radius=4)
        for cell in visualizer.closed_set:
            pygame.draw.rect(ui.screen, (87, 72, 133), self._cell_rect(cell), border_radius=4)
        if visualizer.path:
            for cell in visualizer.path:
                pygame.draw.rect(ui.screen, (238, 192, 70), self._cell_rect(cell), width=3, border_radius=4)
        if self.replay_result:
            for cell in self.replay_result.path:
                pygame.draw.rect(ui.screen, (107, 177, 255), self._cell_rect(cell), width=1, border_radius=4)
        if visualizer.selected_cell:
            pygame.draw.rect(ui.screen, (255, 255, 255), self._cell_rect(visualizer.selected_cell), width=2, border_radius=5)
        for cell, label_color in ((visualizer.start, (120, 225, 153)), (visualizer.goal, (255, 126, 137))):
            if cell:
                pygame.draw.circle(ui.screen, label_color, ui._cell_center(cell), 5)

    def _cell_rect(self, cell):
        import pygame
        ui = self.ui
        return pygame.Rect(ui.GRID_X + cell[0] * ui.cell_size + 3,
                           ui.GRID_Y + cell[1] * ui.cell_size + 3,
                           ui.cell_size - 6, ui.cell_size - 6)

    def draw_search_panel(self, rect):
        ui, v = self.ui, self.visualizer
        import pygame
        ui._draw_panel(rect, "A* search visualizer · click grid: start, then goal", (70, 196, 177))
        ui._draw_text(f"Open {len(v.open_set)}  ·  Closed {len(v.closed_set)}  ·  Query {v.start or '—'} → {v.goal or '—'}", rect.x + 14, rect.y + 31, ui.MUTED, ui.tiny)
        if v.selected_cell:
            vals = v.values(v.selected_cell)
            g_str = f"{vals['g']:.1f}" if vals.get("g") is not None else "—"
            h_str = f"{vals['h']:.1f}" if vals.get("h") is not None else "—"
            f_str = f"{vals['f']:.1f}" if vals.get("f") is not None else "—"
            ui._draw_text(f"Selected {v.selected_cell}   g={g_str}   h={h_str}   f={f_str}", rect.x + 14, rect.y + 51, ui.TEXT, ui.small)
        else:
            ui._draw_text("A* expands the lowest f = g + h cell each frame.", rect.x + 14, rect.y + 51, ui.TEXT, ui.small)
        status = "Path found" if v.success else "No path" if v.done else "Searching…" if v.start else "Choose two traversable grid cells"
        ui._draw_text(f"{status}  ·  Path length {len(v.path)}", rect.x + 14, rect.y + 76, (238, 192, 70), ui.tiny)
        label = f"Compare: {self.replay_planner}  ›"
        button_rect = pygame.Rect(rect.x + rect.width - 180, rect.y + 40, 160, 30)
        ui._button("search_compare", label, button_rect)
        if self.replay_result:
            result = self.replay_result
            ui._draw_text(f"{result.planner_name}: {len(result.path)} cells · cost {result.cost:.1f} · expanded {result.nodes_expanded}", rect.x + 14, rect.y + 103, ui.TEXT, ui.tiny)

    def draw_decision_panel(self, rect):
        ui = self.ui
        import pygame
        ui._draw_panel(rect, "Decision explainer · read-only", (183, 153, 255))
        lines = self.explainer.latest_assignment(ui.sim.delivery_manager)
        for drone in ui.sim.drones.values():
            if drone.replan_event_log or drone.state.value in ("GOING_TO_CHARGE", "CHARGING"):
                lines += self.explainer.drone_reason(
                    drone, ui.sim.env, ui.sim.weather_agent.current_weather.value
                )
                break
        clip = pygame.Rect(rect.x + 10, rect.y + 28, rect.width - 20, rect.height - 36)
        ui.screen.set_clip(clip)
        for idx, line in enumerate(lines[:14]):
            ui._draw_text(line[:140], rect.x + 14, rect.y + 31 + idx * 19, ui.TEXT if idx else (192, 169, 255), ui.tiny)
        ui.screen.set_clip(None)

    def draw_benchmark_panel(self, rect):
        import pygame
        ui = self.ui
        ui._draw_panel(rect, "Fleet scaling benchmark · saved under results/", (102, 179, 255))
        rows = ui.benchmark_rows
        ui._draw_text(ui.benchmark_message, rect.x + 14, rect.y + 31, ui.TEXT, ui.tiny)
        if rows:
            headers = ("DRONES", "DELIVERIES", "ON TIME", "AVG TIME", "DISTANCE", "COLLISIONS", "UTIL")
            w = rect.width
            x_positions = (
                rect.x + 14,
                rect.x + int(w * 0.13),
                rect.x + int(w * 0.28),
                rect.x + int(w * 0.43),
                rect.x + int(w * 0.58),
                rect.x + int(w * 0.73),
                rect.x + int(w * 0.87),
            )
            for x, label in zip(x_positions, headers):
                ui._draw_text(label, x, rect.y + 58, ui.MUTED, ui.tiny)
            for row_idx, row in enumerate(rows[:6]):
                values = (row["fleet_size"], row["deliveries_completed"], f'{row["on_time_rate_pct"]}%', row["average_delivery_time_ticks"], row["total_distance"], row["collisions"], f'{row["utilization_pct"]}%')
                for x, value in zip(x_positions, values):
                    ui._draw_text(value, x, rect.y + 79 + row_idx * 19, ui.TEXT, ui.tiny)
        else:
            ui._draw_text("Shortcut compares 1, 2, 4, 8, and 12 drones on this scenario.", rect.x + 14, rect.y + 57, ui.MUTED, ui.small)
