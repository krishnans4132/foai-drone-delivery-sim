import React, { useRef, useEffect, useState } from 'react';

const DRONE_PALETTE = [
  '#f43f5e', '#38bdf8', '#f59e0b', '#a855f7',
  '#10b981', '#ec4899', '#84cc16', '#fb923c',
  '#06b6d4', '#eab308', '#6366f1', '#14b8a6',
];

export default function GridCanvas({
  grid,
  drones = [],
  requests = [],
  weather = 'Clear',
  selectedCell = null,
  onCellClick = () => {},
  showRoutes = true,
  visualizerData = null,
}) {
  const canvasRef = useRef(null);
  const [hoveredCell, setHoveredCell] = useState(null);
  const animPositionsRef = useRef({}); // { [droneId]: { x, y } }

  const width = grid?.width || 20;
  const height = grid?.height || 20;

  // Track smooth drone positions for 60fps interpolation
  useEffect(() => {
    drones.forEach((d) => {
      if (!animPositionsRef.current[d.id]) {
        animPositionsRef.current[d.id] = { x: d.position[0], y: d.position[1] };
      }
    });
  }, [drones]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;

    let animationId;

    const render = () => {
      // Smoothly nudge animated positions towards target positions
      drones.forEach((d) => {
        const cur = animPositionsRef.current[d.id];
        if (cur) {
          cur.x += (d.position[0] - cur.x) * 0.22;
          cur.y += (d.position[1] - cur.y) * 0.22;
        }
      });

      const rect = canvas.getBoundingClientRect();
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      ctx.scale(dpr, dpr);

      const cellSize = rect.width / width;

      // 1. Clear background
      ctx.fillStyle = '#090e1a';
      ctx.fillRect(0, 0, rect.width, rect.height);

      // 2. Draw Grid Lines
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.04)';
      ctx.lineWidth = 1;
      for (let x = 0; x <= width; x++) {
        ctx.beginPath();
        ctx.moveTo(x * cellSize, 0);
        ctx.lineTo(x * cellSize, height * cellSize);
        ctx.stroke();
      }
      for (let y = 0; y <= height; y++) {
        ctx.beginPath();
        ctx.moveTo(0, y * cellSize);
        ctx.lineTo(width * cellSize, y * cellSize);
        ctx.stroke();
      }

      // Sets for fast lookup
      const obstacleSet = new Set((grid?.obstacles || []).map(([x, y]) => `${x},${y}`));
      const restrictedSet = new Set((grid?.restricted || []).map(([x, y]) => `${x},${y}`));
      const stormSet = new Set((grid?.stormCells || []).map(([x, y]) => `${x},${y}`));

      // 3. Draw Environment Cells
      for (let y = 0; y < height; y++) {
        for (let x = 0; x < width; x++) {
          const key = `${x},${y}`;
          const px = x * cellSize;
          const py = y * cellSize;

          if (obstacleSet.has(key)) {
            // Obstacle (Carbon block)
            ctx.fillStyle = '#1e293b';
            ctx.fillRect(px + 2, py + 2, cellSize - 4, cellSize - 4);
            ctx.strokeStyle = '#334155';
            ctx.lineWidth = 1.5;
            ctx.strokeRect(px + 2, py + 2, cellSize - 4, cellSize - 4);

            // Diagonal cross
            ctx.beginPath();
            ctx.moveTo(px + 4, py + 4);
            ctx.lineTo(px + cellSize - 4, py + cellSize - 4);
            ctx.moveTo(px + cellSize - 4, py + 4);
            ctx.lineTo(px + 4, py + cellSize - 4);
            ctx.stroke();
          } else if (stormSet.has(key)) {
            // Storm Block (Dangerous vortex)
            ctx.fillStyle = 'rgba(244, 63, 94, 0.25)';
            ctx.fillRect(px + 2, py + 2, cellSize - 4, cellSize - 4);
            ctx.strokeStyle = '#f43f5e';
            ctx.lineWidth = 1.5;
            ctx.strokeRect(px + 2, py + 2, cellSize - 4, cellSize - 4);
            // Red warning icon
            ctx.fillStyle = '#f43f5e';
            ctx.font = 'bold 12px monospace';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText('⚡', px + cellSize / 2, py + cellSize / 2);
          } else if (restrictedSet.has(key)) {
            // Restricted Zone
            ctx.fillStyle = 'rgba(168, 85, 247, 0.18)';
            ctx.fillRect(px + 2, py + 2, cellSize - 4, cellSize - 4);
            ctx.strokeStyle = '#a855f7';
            ctx.lineWidth = 1;
            ctx.strokeRect(px + 2, py + 2, cellSize - 4, cellSize - 4);
          }
        }
      }

      // 4. Draw Charging Stations
      (grid?.chargers || []).forEach(([cx, cy]) => {
        const px = cx * cellSize + cellSize / 2;
        const py = cy * cellSize + cellSize / 2;
        ctx.fillStyle = 'rgba(56, 189, 248, 0.15)';
        ctx.beginPath();
        ctx.arc(px, py, cellSize * 0.4, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = '#38bdf8';
        ctx.lineWidth = 1.5;
        ctx.stroke();

        ctx.fillStyle = '#38bdf8';
        ctx.font = `${Math.floor(cellSize * 0.45)}px sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('⚡', px, py);
      });

      // 5. Visualizer Layer (if active)
      if (visualizerData) {
        // Closed set
        ctx.fillStyle = 'rgba(168, 85, 247, 0.35)';
        (visualizerData.closedSet || []).forEach(([x, y]) => {
          ctx.fillRect(x * cellSize + 2, y * cellSize + 2, cellSize - 4, cellSize - 4);
        });
        // Open set
        ctx.fillStyle = 'rgba(16, 185, 129, 0.35)';
        (visualizerData.openSet || []).forEach(([x, y]) => {
          ctx.fillRect(x * cellSize + 2, y * cellSize + 2, cellSize - 4, cellSize - 4);
        });
        // Path
        if (visualizerData.path && visualizerData.path.length > 1) {
          ctx.strokeStyle = '#fbbf24';
          ctx.lineWidth = 3;
          ctx.beginPath();
          visualizerData.path.forEach(([x, y], idx) => {
            const px = x * cellSize + cellSize / 2;
            const py = y * cellSize + cellSize / 2;
            if (idx === 0) ctx.moveTo(px, py);
            else ctx.lineTo(px, py);
          });
          ctx.stroke();
        }
      }

      // 6. Draw Delivery Requests (Pickups & Deliveries)
      requests.forEach((req) => {
        if (req.status === 'DELIVERED' || req.status === 'EXPIRED') return;

        // Pickup (Amber crate)
        if (req.status === 'WAITING' || req.status === 'IN_TRANSIT') {
          const px = req.pickup[0] * cellSize + cellSize / 2;
          const py = req.pickup[1] * cellSize + cellSize / 2;
          ctx.fillStyle = 'rgba(245, 158, 11, 0.2)';
          ctx.beginPath();
          ctx.arc(px, py, cellSize * 0.35, 0, Math.PI * 2);
          ctx.fill();
          ctx.strokeStyle = '#f59e0b';
          ctx.lineWidth = 1.5;
          ctx.stroke();

          ctx.fillStyle = '#f59e0b';
          ctx.font = `${Math.floor(cellSize * 0.42)}px sans-serif`;
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillText('📦', px, py);
        }

        // Destination (Emerald target pad)
        const dx = req.destination[0] * cellSize + cellSize / 2;
        const dy = req.destination[1] * cellSize + cellSize / 2;
        ctx.fillStyle = 'rgba(16, 185, 129, 0.15)';
        ctx.beginPath();
        ctx.arc(dx, dy, cellSize * 0.38, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = '#10b981';
        ctx.lineWidth = 1.8;
        ctx.stroke();
        ctx.beginPath();
        ctx.arc(dx, dy, cellSize * 0.18, 0, Math.PI * 2);
        ctx.stroke();
      });

      // 7. Draw Drone Trails & Planned Routes
      drones.forEach((drone, i) => {
        const color = DRONE_PALETTE[i % DRONE_PALETTE.length];

        // Trails
        if (drone.trail && drone.trail.length > 1) {
          ctx.strokeStyle = color;
          ctx.globalAlpha = 0.35;
          ctx.lineWidth = 2;
          ctx.beginPath();
          drone.trail.forEach(([tx, ty], idx) => {
            const px = tx * cellSize + cellSize / 2;
            const py = ty * cellSize + cellSize / 2;
            if (idx === 0) ctx.moveTo(px, py);
            else ctx.lineTo(px, py);
          });
          ctx.stroke();
          ctx.globalAlpha = 1.0;
        }

        // Planned Route (Dashed Line)
        if (showRoutes && drone.route && drone.route.length > 0) {
          ctx.strokeStyle = color;
          ctx.setLineDash([4, 4]);
          ctx.lineWidth = 2;
          ctx.beginPath();
          const cur = animPositionsRef.current[drone.id] || { x: drone.position[0], y: drone.position[1] };
          ctx.moveTo(cur.x * cellSize + cellSize / 2, cur.y * cellSize + cellSize / 2);
          drone.route.forEach(([rx, ry]) => {
            ctx.lineTo(rx * cellSize + cellSize / 2, ry * cellSize + cellSize / 2);
          });
          ctx.stroke();
          ctx.setLineDash([]);
        }
      });

      // 8. Draw Drones (Interpolated smooth flight)
      drones.forEach((drone, i) => {
        const color = DRONE_PALETTE[i % DRONE_PALETTE.length];
        const cur = animPositionsRef.current[drone.id] || { x: drone.position[0], y: drone.position[1] };
        const px = cur.x * cellSize + cellSize / 2;
        const py = cur.y * cellSize + cellSize / 2;

        // Outer glow
        const gradient = ctx.createRadialGradient(px, py, 2, px, py, cellSize * 0.5);
        gradient.addColorStop(0, color);
        gradient.addColorStop(1, 'transparent');
        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.arc(px, py, cellSize * 0.5, 0, Math.PI * 2);
        ctx.fill();

        // Drone Body
        ctx.fillStyle = '#0f172a';
        ctx.beginPath();
        ctx.arc(px, py, cellSize * 0.32, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.stroke();

        // Carried package indicator
        if (drone.hasPackage) {
          ctx.fillStyle = '#f59e0b';
          ctx.beginPath();
          ctx.arc(px + cellSize * 0.22, py - cellSize * 0.22, 4.5, 0, Math.PI * 2);
          ctx.fill();
        }

        // Label
        ctx.fillStyle = '#ffffff';
        ctx.font = `bold ${Math.floor(cellSize * 0.28)}px sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        const num = drone.id.replace('DRONE-', '');
        ctx.fillText(num, px, py);

        // Battery health bar above drone
        const barW = cellSize * 0.7;
        const barH = 3;
        const barX = px - barW / 2;
        const barY = py - cellSize * 0.38;
        ctx.fillStyle = 'rgba(0,0,0,0.6)';
        ctx.fillRect(barX, barY, barW, barH);
        const batFrac = Math.max(0, Math.min(1, drone.battery / (drone.batteryCapacity || 100)));
        ctx.fillStyle = batFrac > 0.4 ? '#10b981' : batFrac > 0.2 ? '#f59e0b' : '#f43f5e';
        ctx.fillRect(barX, barY, barW * batFrac, barH);
      });

      // 9. Hovered & Selected Cell Highlight
      if (selectedCell) {
        ctx.strokeStyle = '#38bdf8';
        ctx.lineWidth = 2.5;
        ctx.strokeRect(selectedCell[0] * cellSize + 1, selectedCell[1] * cellSize + 1, cellSize - 2, cellSize - 2);
      }
      if (hoveredCell) {
        ctx.fillStyle = 'rgba(255, 255, 255, 0.08)';
        ctx.fillRect(hoveredCell[0] * cellSize, hoveredCell[1] * cellSize, cellSize, cellSize);
      }

      animationId = requestAnimationFrame(render);
    };

    animationId = requestAnimationFrame(render);
    return () => cancelAnimationFrame(animationId);
  }, [grid, drones, requests, weather, selectedCell, hoveredCell, showRoutes, visualizerData, width, height]);

  const handleMouseMove = (e) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const cellSize = rect.width / width;
    const x = Math.floor((e.clientX - rect.left) / cellSize);
    const y = Math.floor((e.clientY - rect.top) / cellSize);
    if (x >= 0 && x < width && y >= 0 && y < height) {
      setHoveredCell([x, y]);
    } else {
      setHoveredCell(null);
    }
  };

  const handleClick = (e) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const cellSize = rect.width / width;
    const x = Math.floor((e.clientX - rect.left) / cellSize);
    const y = Math.floor((e.clientY - rect.top) / cellSize);
    if (x >= 0 && x < width && y >= 0 && y < height) {
      onCellClick([x, y]);
    }
  };

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%', minHeight: '560px' }}>
      <canvas
        ref={canvasRef}
        onMouseMove={handleMouseMove}
        onMouseLeave={() => setHoveredCell(null)}
        onClick={handleClick}
        style={{
          width: '100%',
          height: '100%',
          borderRadius: '12px',
          display: 'block',
          cursor: 'crosshair',
        }}
      />
    </div>
  );
}
