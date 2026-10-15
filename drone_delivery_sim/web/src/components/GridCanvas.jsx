import React, { useRef, useEffect, useState } from 'react';

// Cohesive, high-contrast palette for drones (electric blue primary, followed by crisp secondary tones)
const DRONE_PALETTE = [
  '#3B82F6', // Electric Blue (Primary)
  '#10B981', // Emerald Green
  '#8B5CF6', // Purple
  '#F59E0B', // Amber
  '#06B6D4', // Cyan
  '#EC4899', // Pink
  '#84CC16', // Lime
  '#F97316', // Orange
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
  const containerRef = useRef(null);
  const [hoveredCell, setHoveredCell] = useState(null);
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });
  const animPositionsRef = useRef({}); // { [droneId]: { x, y } }

  const width = grid?.width || 20;
  const height = grid?.height || 20;

  // Track smooth drone positions
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
      // Smoothly interpolate animated positions towards target positions
      drones.forEach((d) => {
        const cur = animPositionsRef.current[d.id];
        if (cur) {
          cur.x += (d.position[0] - cur.x) * 0.28;
          cur.y += (d.position[1] - cur.y) * 0.28;
        }
      });

      const rect = canvas.getBoundingClientRect();
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      ctx.scale(dpr, dpr);

      // Perfect square sizing: board fills the available space with no awkward margins
      const availableSize = Math.min(rect.width, rect.height);
      const cellSize = availableSize / Math.max(width, height);
      const gridPixelW = cellSize * width;
      const gridPixelH = cellSize * height;
      const offsetX = (rect.width - gridPixelW) / 2;
      const offsetY = (rect.height - gridPixelH) / 2;

      // 1. Board Background Surface (#12151A)
      ctx.fillStyle = '#12151A';
      ctx.fillRect(0, 0, rect.width, rect.height);

      ctx.save();
      ctx.translate(offsetX, offsetY);

      // 2. Subtle Grid Lines (#1A1F26)
      ctx.strokeStyle = '#1A1F26';
      ctx.lineWidth = 1;
      for (let x = 0; x <= width; x++) {
        ctx.beginPath();
        ctx.moveTo(x * cellSize, 0);
        ctx.lineTo(x * cellSize, gridPixelH);
        ctx.stroke();
      }
      for (let y = 0; y <= height; y++) {
        ctx.beginPath();
        ctx.moveTo(0, y * cellSize);
        ctx.lineTo(gridPixelW, y * cellSize);
        ctx.stroke();
      }

      // Fast entity coordinate lookups
      const obstacleSet = new Set((grid?.obstacles || []).map(([x, y]) => `${x},${y}`));
      const restrictedSet = new Set((grid?.restricted || []).map(([x, y]) => `${x},${y}`));
      const stormSet = new Set((grid?.stormCells || []).map(([x, y]) => `${x},${y}`));

      // 3. Environmental Cells (Obstacles, Restricted Airspace, Storm Areas)
      for (let y = 0; y < height; y++) {
        for (let x = 0; x < width; x++) {
          const key = `${x},${y}`;
          const px = x * cellSize;
          const py = y * cellSize;
          const pad = 2;
          const sz = cellSize - pad * 2;
          const cx = px + cellSize / 2;
          const cy = py + cellSize / 2;

          if (obstacleSet.has(key)) {
            // Solid gray block with clean 'X' / ban icon
            ctx.fillStyle = '#1E232B';
            ctx.fillRect(px + pad, py + pad, sz, sz);
            ctx.strokeStyle = '#2E3642';
            ctx.lineWidth = 1;
            ctx.strokeRect(px + pad, py + pad, sz, sz);

            // X Icon
            const xOffset = cellSize * 0.22;
            ctx.strokeStyle = '#6B7280';
            ctx.lineWidth = 1.8;
            ctx.beginPath();
            ctx.moveTo(cx - xOffset, cy - xOffset);
            ctx.lineTo(cx + xOffset, cy + xOffset);
            ctx.moveTo(cx + xOffset, cy - xOffset);
            ctx.lineTo(cx - xOffset, cy + xOffset);
            ctx.stroke();
          } else if (stormSet.has(key)) {
            // Storm area: Red translucent cell with cloud-lightning icon
            ctx.fillStyle = 'rgba(239, 68, 68, 0.14)';
            ctx.fillRect(px + pad, py + pad, sz, sz);
            ctx.strokeStyle = 'rgba(239, 68, 68, 0.45)';
            ctx.lineWidth = 1;
            ctx.strokeRect(px + pad, py + pad, sz, sz);

            // Vector Cloud-Lightning Icon
            ctx.strokeStyle = '#EF4444';
            ctx.fillStyle = '#EF4444';
            ctx.lineWidth = 1.2;
            
            // Cloud top arcs
            ctx.beginPath();
            ctx.arc(cx - 3, cy - 3, 3, Math.PI * 0.8, Math.PI * 1.8);
            ctx.arc(cx + 2, cy - 4, 3.5, Math.PI * 1.1, Math.PI * 2.1);
            ctx.stroke();

            // Lightning Bolt
            ctx.beginPath();
            ctx.moveTo(cx + 1, cy - 1);
            ctx.lineTo(cx - 2, cy + 3);
            ctx.lineTo(cx + 1, cy + 3);
            ctx.lineTo(cx - 1, cy + 7);
            ctx.lineTo(cx + 3, cy + 2);
            ctx.lineTo(cx, cy + 2);
            ctx.closePath();
            ctx.fill();
          } else if (restrictedSet.has(key)) {
            // Restricted Airspace: Diagonal hatch pattern + dashed border + shield-alert icon
            ctx.save();
            ctx.beginPath();
            ctx.rect(px + pad, py + pad, sz, sz);
            ctx.clip();

            // Diagonal hatch
            ctx.strokeStyle = 'rgba(100, 116, 139, 0.25)';
            ctx.lineWidth = 1;
            for (let d = -cellSize; d < cellSize * 2; d += 6) {
              ctx.beginPath();
              ctx.moveTo(px + d, py);
              ctx.lineTo(px + d + cellSize, py + cellSize);
              ctx.stroke();
            }
            ctx.restore();

            // Dashed Border
            ctx.strokeStyle = '#475569';
            ctx.setLineDash([3, 3]);
            ctx.lineWidth = 1;
            ctx.strokeRect(px + pad, py + pad, sz, sz);
            ctx.setLineDash([]);

            // Shield icon in center
            ctx.fillStyle = '#64748B';
            ctx.beginPath();
            ctx.moveTo(cx, cy - 5);
            ctx.lineTo(cx + 4, cy - 3);
            ctx.lineTo(cx + 4, cy + 1);
            ctx.lineTo(cx, cy + 5);
            ctx.lineTo(cx - 4, cy + 1);
            ctx.lineTo(cx - 4, cy - 3);
            ctx.closePath();
            ctx.fill();

            // Exclamation inside shield
            ctx.fillStyle = '#12151A';
            ctx.font = 'bold 7px monospace';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText('!', cx, cy - 0.5);
          }
        }
      }

      // 4. Charging Stations (Blue ring with zap lightning icon)
      (grid?.chargers || []).forEach(([cx, cy]) => {
        const px = cx * cellSize + cellSize / 2;
        const py = cy * cellSize + cellSize / 2;
        const r = cellSize * 0.38;

        ctx.fillStyle = 'rgba(59, 130, 246, 0.12)';
        ctx.beginPath();
        ctx.arc(px, py, r, 0, Math.PI * 2);
        ctx.fill();

        ctx.strokeStyle = '#3B82F6';
        ctx.lineWidth = 1.5;
        ctx.stroke();

        // Vector Zap Icon
        ctx.fillStyle = '#3B82F6';
        ctx.beginPath();
        ctx.moveTo(px + 1, py - 6);
        ctx.lineTo(px - 3, py + 1);
        ctx.lineTo(px, py + 1);
        ctx.lineTo(px - 1, py + 6);
        ctx.lineTo(px + 4, py - 1);
        ctx.lineTo(px + 1, py - 1);
        ctx.closePath();
        ctx.fill();
      });

      // 5. Visualizer Layer (A* Search Lab)
      if (visualizerData) {
        // Closed set (explored)
        ctx.fillStyle = 'rgba(139, 92, 246, 0.2)';
        (visualizerData.closedSet || []).forEach(([x, y]) => {
          ctx.fillRect(x * cellSize + 1.5, y * cellSize + 1.5, cellSize - 3, cellSize - 3);
        });
        // Open set (frontier)
        ctx.fillStyle = 'rgba(16, 185, 129, 0.2)';
        (visualizerData.openSet || []).forEach(([x, y]) => {
          ctx.fillRect(x * cellSize + 1.5, y * cellSize + 1.5, cellSize - 3, cellSize - 3);
        });
        // Optimal Path
        if (visualizerData.path && visualizerData.path.length > 1) {
          ctx.strokeStyle = '#3B82F6';
          ctx.lineWidth = 2.5;
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

      // 6. Delivery Requests (Pickup points & Destination targets)
      requests.forEach((req) => {
        if (req.status === 'DELIVERED' || req.status === 'EXPIRED') return;

        // Pickup point: Amber rounded square with vector package box icon
        if (req.status === 'WAITING' || req.status === 'IN_TRANSIT') {
          const px = req.pickup[0] * cellSize + cellSize / 2;
          const py = req.pickup[1] * cellSize + cellSize / 2;
          const boxSize = Math.floor(cellSize * 0.62);
          const half = boxSize / 2;

          ctx.fillStyle = 'rgba(245, 158, 11, 0.15)';
          ctx.fillRect(px - half, py - half, boxSize, boxSize);
          ctx.strokeStyle = '#F59E0B';
          ctx.lineWidth = 1.5;
          ctx.strokeRect(px - half, py - half, boxSize, boxSize);

          // Package Box Icon
          ctx.strokeStyle = '#F59E0B';
          ctx.lineWidth = 1.2;
          ctx.beginPath();
          // Horizontal ribbon
          ctx.moveTo(px - half, py);
          ctx.lineTo(px + half, py);
          // Vertical ribbon
          ctx.moveTo(px, py - half);
          ctx.lineTo(px, py + half);
          ctx.stroke();
        }

        // Destination target: Green ring with vector map-pin icon
        const dx = req.destination[0] * cellSize + cellSize / 2;
        const dy = req.destination[1] * cellSize + cellSize / 2;
        const targetR = cellSize * 0.38;

        ctx.strokeStyle = '#10B981';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(dx, dy, targetR, 0, Math.PI * 2);
        ctx.stroke();

        ctx.fillStyle = 'rgba(16, 185, 129, 0.12)';
        ctx.fill();

        // Vector Map-Pin Icon
        ctx.fillStyle = '#10B981';
        ctx.beginPath();
        ctx.arc(dx, dy - 2, 3.5, 0, Math.PI * 2);
        ctx.fill();
        ctx.beginPath();
        ctx.moveTo(dx - 3, dy - 1);
        ctx.lineTo(dx, dy + 5);
        ctx.lineTo(dx + 3, dy - 1);
        ctx.closePath();
        ctx.fill();
        // Inner pin hole
        ctx.fillStyle = '#12151A';
        ctx.beginPath();
        ctx.arc(dx, dy - 2, 1.2, 0, Math.PI * 2);
        ctx.fill();
      });

      // 7. Drone Trails & Planned Routes with Direction Arrows
      drones.forEach((drone, i) => {
        const color = DRONE_PALETTE[i % DRONE_PALETTE.length];

        // Smooth subtle trail
        if (drone.trail && drone.trail.length > 1) {
          ctx.strokeStyle = color;
          ctx.globalAlpha = 0.22;
          ctx.lineWidth = 1.5;
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

        // Planned Route: 2px line with direction arrows in drone's color
        if (showRoutes && drone.route && drone.route.length > 0) {
          ctx.strokeStyle = color;
          ctx.lineWidth = 2;
          ctx.setLineDash([4, 4]);
          ctx.beginPath();
          const cur = animPositionsRef.current[drone.id] || { x: drone.position[0], y: drone.position[1] };
          let prevX = cur.x * cellSize + cellSize / 2;
          let prevY = cur.y * cellSize + cellSize / 2;
          ctx.moveTo(prevX, prevY);

          drone.route.forEach(([rx, ry]) => {
            const nextX = rx * cellSize + cellSize / 2;
            const nextY = ry * cellSize + cellSize / 2;
            ctx.lineTo(nextX, nextY);
          });
          ctx.stroke();
          ctx.setLineDash([]);

          // Draw direction arrows along the route
          drone.route.forEach(([rx, ry], idx) => {
            if (idx % 2 === 0) {
              const startX = idx === 0 ? prevX : drone.route[idx - 1][0] * cellSize + cellSize / 2;
              const startY = idx === 0 ? prevY : drone.route[idx - 1][1] * cellSize + cellSize / 2;
              const targetX = rx * cellSize + cellSize / 2;
              const targetY = ry * cellSize + cellSize / 2;
              const angle = Math.atan2(targetY - startY, targetX - startX);
              const midX = (startX + targetX) / 2;
              const midY = (startY + targetY) / 2;

              ctx.fillStyle = color;
              ctx.beginPath();
              ctx.moveTo(midX + Math.cos(angle) * 4, midY + Math.sin(angle) * 4);
              ctx.lineTo(midX + Math.cos(angle + 2.5) * 4, midY + Math.sin(angle + 2.5) * 4);
              ctx.lineTo(midX + Math.cos(angle - 2.5) * 4, midY + Math.sin(angle - 2.5) * 4);
              ctx.closePath();
              ctx.fill();
            }
          });
        }
      });

      // 8. Drones (Identifiable by shape and vector plane icon)
      drones.forEach((drone, i) => {
        const color = DRONE_PALETTE[i % DRONE_PALETTE.length];
        const cur = animPositionsRef.current[drone.id] || { x: drone.position[0], y: drone.position[1] };
        const px = cur.x * cellSize + cellSize / 2;
        const py = cur.y * cellSize + cellSize / 2;
        const radius = cellSize * 0.36;

        if (drone.isBroken) {
          // Faulty/Broken Drone: Red outline, dark red interior, triangle-alert icon
          ctx.fillStyle = '#1F1214';
          ctx.beginPath();
          ctx.arc(px, py, radius, 0, Math.PI * 2);
          ctx.fill();

          ctx.strokeStyle = '#EF4444';
          ctx.lineWidth = 2.5;
          ctx.stroke();

          // Triangle Alert Icon in center
          ctx.fillStyle = '#EF4444';
          ctx.beginPath();
          ctx.moveTo(px, py - 6);
          ctx.lineTo(px + 6, py + 4);
          ctx.lineTo(px - 6, py + 4);
          ctx.closePath();
          ctx.fill();

          ctx.fillStyle = '#1F1214';
          ctx.font = 'bold 8px monospace';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillText('!', px, py + 0.5);
        } else {
          // Operational Drone: Filled dark disc with 2px drone-color border
          ctx.fillStyle = '#12151A';
          ctx.beginPath();
          ctx.arc(px, py, radius, 0, Math.PI * 2);
          ctx.fill();

          ctx.strokeStyle = color;
          ctx.lineWidth = 2;
          ctx.stroke();

          // Stylized Plane / Quadcopter silhouette
          ctx.strokeStyle = 'rgba(255, 255, 255, 0.4)';
          ctx.lineWidth = 1.2;
          ctx.beginPath();
          // Diagonal rotor arms
          ctx.moveTo(px - 4, py - 4);
          ctx.lineTo(px + 4, py + 4);
          ctx.moveTo(px + 4, py - 4);
          ctx.lineTo(px - 4, py + 4);
          ctx.stroke();

          // Drone ID number in center
          ctx.fillStyle = '#E6E8EB';
          ctx.font = `700 ${Math.max(10, Math.floor(cellSize * 0.28))}px 'JetBrains Mono', monospace`;
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          const num = drone.id.replace('DRONE-', '');
          ctx.fillText(num, px, py);
        }

        // Cargo Indicator (if carrying package)
        if (drone.hasPackage) {
          ctx.fillStyle = '#F59E0B';
          ctx.beginPath();
          ctx.arc(px + radius * 0.75, py - radius * 0.75, 4, 0, Math.PI * 2);
          ctx.fill();
          ctx.strokeStyle = '#12151A';
          ctx.lineWidth = 1;
          ctx.stroke();
        }

        // Battery Bar below drone
        const barW = Math.floor(cellSize * 0.7);
        const barH = 3;
        const barX = px - barW / 2;
        const barY = py + radius + 3;
        ctx.fillStyle = '#232830';
        ctx.fillRect(barX, barY, barW, barH);
        const batFrac = Math.max(0, Math.min(1, drone.battery / (drone.batteryCapacity || 100)));
        ctx.fillStyle = batFrac > 0.4 ? '#10B981' : batFrac > 0.2 ? '#F59E0B' : '#EF4444';
        ctx.fillRect(barX, barY, barW * batFrac, barH);
      });

      // 9. Selected & Hovered Cell Highlighting
      if (selectedCell) {
        ctx.strokeStyle = '#3B82F6';
        ctx.lineWidth = 2;
        ctx.strokeRect(selectedCell[0] * cellSize + 1, selectedCell[1] * cellSize + 1, cellSize - 2, cellSize - 2);
      }
      if (hoveredCell) {
        ctx.fillStyle = 'rgba(255, 255, 255, 0.05)';
        ctx.fillRect(hoveredCell[0] * cellSize, hoveredCell[1] * cellSize, cellSize, cellSize);
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.2)';
        ctx.lineWidth = 1;
        ctx.strokeRect(hoveredCell[0] * cellSize, hoveredCell[1] * cellSize, cellSize, cellSize);
      }

      ctx.restore();

      animationId = requestAnimationFrame(render);
    };

    animationId = requestAnimationFrame(render);
    return () => cancelAnimationFrame(animationId);
  }, [grid, drones, requests, weather, selectedCell, hoveredCell, showRoutes, visualizerData, width, height]);

  // Mouse event handlers for coordinates and tooltips
  const getCellFromEvent = (e) => {
    const canvas = canvasRef.current;
    if (!canvas) return null;
    const rect = canvas.getBoundingClientRect();
    const availableSize = Math.min(rect.width, rect.height);
    const cellSize = availableSize / Math.max(width, height);
    const gridPixelW = cellSize * width;
    const gridPixelH = cellSize * height;
    const offsetX = (rect.width - gridPixelW) / 2;
    const offsetY = (rect.height - gridPixelH) / 2;

    const mouseX = e.clientX - rect.left - offsetX;
    const mouseY = e.clientY - rect.top - offsetY;

    if (mouseX < 0 || mouseX >= gridPixelW || mouseY < 0 || mouseY >= gridPixelH) {
      return null;
    }

    const x = Math.floor(mouseX / cellSize);
    const y = Math.floor(mouseY / cellSize);
    if (x >= 0 && x < width && y >= 0 && y < height) {
      return [x, y];
    }
    return null;
  };

  const handleMouseMove = (e) => {
    const cell = getCellFromEvent(e);
    setHoveredCell(cell);
    const rect = containerRef.current?.getBoundingClientRect();
    if (rect) {
      setMousePos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
    }
  };

  const handleClick = (e) => {
    const cell = getCellFromEvent(e);
    if (cell) {
      onCellClick(cell);
    }
  };

  // Inspect entity on hovered cell for rich tooltip
  const getHoveredEntityInfo = () => {
    if (!hoveredCell) return null;
    const [hx, hy] = hoveredCell;

    // Check drone
    const drone = drones.find((d) => d.position[0] === hx && d.position[1] === hy);
    if (drone) {
      return {
        type: drone.isBroken ? 'FAULTY DRONE' : 'ACTIVE DRONE',
        name: drone.id,
        status: drone.isBroken ? 'MECHANICAL FAULT' : `${drone.state} (${drone.batteryPct}% batt)`,
        color: drone.isBroken ? '#EF4444' : '#3B82F6',
      };
    }

    // Check pickup
    const pickupReq = requests.find((r) => r.pickup[0] === hx && r.pickup[1] === hy && r.status !== 'DELIVERED');
    if (pickupReq) {
      return {
        type: 'PICKUP POINT',
        name: pickupReq.id,
        status: `Deadline: tick ${pickupReq.deadline} · ${pickupReq.status}`,
        color: '#F59E0B',
      };
    }

    // Check destination target
    const destReq = requests.find((r) => r.destination[0] === hx && r.destination[1] === hy && r.status !== 'DELIVERED');
    if (destReq) {
      return {
        type: 'DELIVERY TARGET',
        name: destReq.id,
        status: `Destination for ${destReq.id}`,
        color: '#10B981',
      };
    }

    // Check charging hub
    const isCharger = (grid?.chargers || []).some(([cx, cy]) => cx === hx && cy === hy);
    if (isCharger) {
      return {
        type: 'CHARGING HUB',
        name: 'Rapid Charger',
        status: 'Occupancy auto-managed',
        color: '#3B82F6',
      };
    }

    // Check obstacle
    const isObstacle = (grid?.obstacles || []).some(([ox, oy]) => ox === hx && oy === hy);
    if (isObstacle) {
      return {
        type: 'OBSTACLE',
        name: 'Impassable Structure',
        status: 'Collision hazard',
        color: '#6B7280',
      };
    }

    // Check restricted zone
    const isRestricted = (grid?.restricted || []).some(([rx, ry]) => rx === hx && ry === hy);
    if (isRestricted) {
      return {
        type: 'RESTRICTED AIRSPACE',
        name: 'No-Fly Corridor',
        status: 'Permit / caution required',
        color: '#8A919C',
      };
    }

    // Check storm area
    const isStorm = (grid?.stormCells || []).some(([sx, sy]) => sx === hx && sy === hy);
    if (isStorm) {
      return {
        type: 'STORM AREA',
        name: 'Severe Vortex Cell',
        status: 'High drain & turbulence',
        color: '#EF4444',
      };
    }

    return {
      type: 'AIRSPACE CELL',
      name: `(${hx}, ${hy})`,
      status: 'Open traversable cell',
      color: '#8A919C',
    };
  };

  const hoverInfo = getHoveredEntityInfo();

  return (
    <div
      ref={containerRef}
      style={{
        position: 'relative',
        width: '100%',
        aspectRatio: '1 / 1',
        margin: '0 auto',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <canvas
        ref={canvasRef}
        onMouseMove={handleMouseMove}
        onMouseLeave={() => setHoveredCell(null)}
        onClick={handleClick}
        style={{
          width: '100%',
          height: '100%',
          borderRadius: '8px',
          display: 'block',
          cursor: 'crosshair',
        }}
      />

      {/* Floating Hover Tooltip */}
      {hoveredCell && hoverInfo && (
        <div
          style={{
            position: 'absolute',
            left: `${Math.min(Math.max(mousePos.x + 12, 10), (containerRef.current?.clientWidth || 500) - 170)}px`,
            top: `${Math.max(mousePos.y - 48, 10)}px`,
            pointerEvents: 'none',
            background: '#161A22',
            border: '1px solid #2D333F',
            borderRadius: '6px',
            padding: '6px 10px',
            zIndex: 30,
            boxShadow: '0 4px 12px rgba(0, 0, 0, 0.5)',
            display: 'flex',
            flexDirection: 'column',
            gap: '2px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
            <span style={{ fontSize: '10px', fontWeight: '700', color: hoverInfo.color, letterSpacing: '0.4px' }}>
              {hoverInfo.type}
            </span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: '#8A919C' }}>
              [{hoveredCell[0]}, {hoveredCell[1]}]
            </span>
          </div>
          <div style={{ fontSize: '11px', fontWeight: '600', color: '#E6E8EB' }}>
            {hoverInfo.name}
          </div>
          <div style={{ fontSize: '10px', color: '#8A919C' }}>
            {hoverInfo.status}
          </div>
        </div>
      )}
    </div>
  );
}
