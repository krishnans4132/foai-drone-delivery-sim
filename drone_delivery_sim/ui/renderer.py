"""ui.renderer

Pygame-based graphical user interface for the Simulated Drone Delivery System.
Displays the 2D grid, obstacles, weather overlay, charging stations, package destinations,
and active drone states (position, path, battery).
Provides live interactive controls to add (+) or remove (-) drones dynamically at runtime.
Completely decoupled from the core AI logic in sim/.
"""

from typing import Any, Optional


class UIRenderer:
    """Renders the grid environment, weather conditions, and drone fleet using Pygame.

    Attributes:
        sim (Any): Reference to the Simulation engine.
        cell_size (int): Screen pixel dimension per grid cell.
    """

    def __init__(self, sim: Any, cell_size: int = 36):
        """Initialize renderer dimensions and colors."""
        self.sim = sim
        self.cell_size = cell_size
        self.screen = None
        self.clock = None
        self.is_running = False

    def init_display(self) -> None:
        """Initialize Pygame window and assets."""
        import pygame
        pygame.init()
        width = self.sim.env.width * self.cell_size + 300  # Extra space for dashboard sidebar
        height = self.sim.env.height * self.cell_size
        self.screen = pygame.display.set_mode((width, height))
        pygame.display.set_caption("FOAI Drone Delivery System - 23CSE401")
        self.clock = pygame.time.Clock()
        self.is_running = True

    def handle_events(self) -> bool:
        """Handle keyboard and window events.

        Supports dynamic fleet modification:
        - '+' or '=' key: Add drone
        - '-' key: Remove drone
        - Space: Pause / Play
        """
        import pygame
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.is_running = False
                return False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_PLUS, pygame.K_EQUALS):
                    added = self.sim.add_drone()
                    print(f"Dynamic Fleet: {'Added drone' if added else 'Cannot add drone (no free slot)'}")
                elif event.key == pygame.K_MINUS:
                    removed = self.sim.remove_drone()
                    print(f"Dynamic Fleet: {'Removed drone' if removed else 'Cannot remove (minimum 1 drone)'}")
        return True

    def render(self) -> None:
        """Draw one frame of the simulation grid and telemetry sidebar."""
        # Full rendering implementation in Step 8
        pass

    def run_loop(self) -> None:
        """Main UI event and render loop."""
        self.init_display()
        while self.is_running:
            if not self.handle_events():
                break
            self.sim.step()
            self.render()
            self.clock.tick(5)
        import pygame
        pygame.quit()
