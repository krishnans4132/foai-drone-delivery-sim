"""sim.test_scenarios

Pre-configured, repeatable dynamic test scenarios designed for live demonstration
and evaluation of the multi-agent drone delivery system.

Each test scenario bundles a specific set of environmental and hardware conditions:
- Dynamic weather shifts (Clear, Windy, Rain, Storm)
- Scheduled in-flight drone mechanical breakdowns & autonomous task re-allocation
- Emergency battery drains (< 25% threshold) & charging hub convergence
- Dynamic roadblock/storm cell injection triggering 4-step A* replanning
- Narrow-corridor multi-drone conflict resolution with 0 collisions
"""

from typing import Dict, Any, List

TEST_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "test_storm_replan": {
        "id": "test_storm_replan",
        "title": "Test 1: Sudden Storm & 4-Step Dynamic Replanning",
        "category": "Dynamic Replanning",
        "summary": "Sudden storm front and vortex blocks active flight path; drone executes 4-step dynamic A* replan around hazards.",
        "objective": "Verify that when weather escalates from Windy to Storm and a waypoint becomes impassable, the drone perceives the change, confirms route unsuitability, recomputes an alternate A* path, and continues without collision.",
        "conditions": {
            "initial_weather": "Windy (1.5x drain)",
            "scheduled_shift": "Severe Storm (3.0x drain) at Tick 6",
            "hazard": "Storm vortex cell blocks flight corridor at Tick 8",
            "fleet_size": 3,
            "requests": 3,
        },
        "seed": 42,
        "scenario_name": "default",
        "initial_weather": "Windy",
        "fleet_size": 3,
        "custom_requests": [
            {"id": "REQ-T1-01", "pickup": [2, 5], "destination": [18, 18], "deadline": 80},
            {"id": "REQ-T1-02", "pickup": [12, 2], "destination": [2, 16], "deadline": 90},
            {"id": "REQ-T1-03", "pickup": [15, 12], "destination": [4, 4], "deadline": 95},
        ],
        "scheduled_events": [
            {
                "tick": 6,
                "action": "weather",
                "weather": "Storm",
                "log": "[TEST EVENT · TICK 6] Atmospheric pressure drops: Storm weather declared (3.0x energy expenditure).",
            },
            {
                "tick": 8,
                "action": "roadblock_path",
                "log": "[TEST EVENT · TICK 8] Severe storm vortex cell spawned directly ahead on active drone flight path.",
            },
        ],
        "checkpoints": [
            {"id": "cp1", "label": "Fleet dispatched on initial optimal A* routes", "min_tick": 1},
            {"id": "cp2", "label": "Weather shifts to Severe Storm at Tick 6", "min_tick": 6},
            {"id": "cp3", "label": "Dynamic obstacle/vortex detected on route at Tick 8", "min_tick": 8},
            {"id": "cp4", "label": "4-Step Dynamic A* replan executed (detour calculated)", "min_tick": 9},
            {"id": "cp5", "label": "Safe delivery achieved with 0 collisions", "min_tick": 24},
        ],
    },

    "test_breakdown_handoff": {
        "id": "test_breakdown_handoff",
        "title": "Test 2: In-Flight Drone Failure & Autonomous Task Handoff",
        "category": "Fault Tolerance & Re-allocation",
        "summary": "Drone-01 suffers motor breakdown mid-flight; delivery manager re-allocates package to backup drone.",
        "objective": "Verify multi-agent fault tolerance: when a drone carrying a package fails, the package is safely dropped/preserved at its coordinates, returned to the Delivery Manager's queue, and dispatched to an available backup drone.",
        "conditions": {
            "initial_weather": "Clear (1.0x drain)",
            "fleet_size": 3,
            "fault": "DRONE-01 mechanical breakdown injected at Tick 10",
            "recovery": "Autonomous Delivery Manager re-allocation to DRONE-02",
            "requests": 2,
        },
        "seed": 105,
        "scenario_name": "simple_clear",
        "initial_weather": "Clear",
        "fleet_size": 3,
        "custom_requests": [
            {"id": "REQ-T2-01", "pickup": [1, 2], "destination": [16, 16], "deadline": 70},
            {"id": "REQ-T2-02", "pickup": [10, 14], "destination": [3, 4], "deadline": 80},
        ],
        "scheduled_events": [
            {
                "tick": 10,
                "action": "breakdown",
                "drone_id": "DRONE-01",
                "log": "[TEST EVENT · TICK 10] Mechanical motor breakdown injected on DRONE-01. Actuators halted.",
            },
        ],
        "checkpoints": [
            {"id": "cp1", "label": "DRONE-01 picks up package REQ-T2-01 and enters transit", "min_tick": 3},
            {"id": "cp2", "label": "Hardware fault injected on DRONE-01 at Tick 10 (enters FAULT state)", "min_tick": 10},
            {"id": "cp3", "label": "Delivery Manager safely returns package to pool for re-allocation", "min_tick": 11},
            {"id": "cp4", "label": "Backup DRONE-02 dispatched to retrieve stranded package", "min_tick": 12},
            {"id": "cp5", "label": "Package successfully delivered by backup drone", "min_tick": 28},
        ],
    },

    "test_battery_divert": {
        "id": "test_battery_divert",
        "title": "Test 3: Low-Battery Emergency & Multi-Charger Negotiation",
        "category": "Battery Safety & Detours",
        "summary": "Simultaneous battery drain on multiple drones forces emergency recharge detours and charger reservation.",
        "objective": "Verify internal battery threshold safety: when battery drops below 25%, drones divert to the nearest available charging station, coordinate occupancy so two drones do not occupy the same pad, charge to 100%, and resume deliveries.",
        "conditions": {
            "initial_weather": "Rain (2.0x energy consumption)",
            "fleet_size": 4,
            "fault": "DRONE-01 & DRONE-02 batteries drained to 12% at Tick 8",
            "charging_stations": "4 stations available across grid",
            "requests": 4,
        },
        "seed": 77,
        "scenario_name": "default",
        "initial_weather": "Rain",
        "fleet_size": 4,
        "custom_requests": [
            {"id": "REQ-T3-01", "pickup": [2, 5], "destination": [17, 17], "deadline": 90},
            {"id": "REQ-T3-02", "pickup": [12, 2], "destination": [2, 16], "deadline": 90},
            {"id": "REQ-T3-03", "pickup": [15, 12], "destination": [4, 4], "deadline": 90},
            {"id": "REQ-T3-04", "pickup": [7, 8], "destination": [16, 6], "deadline": 90},
        ],
        "scheduled_events": [
            {
                "tick": 8,
                "action": "drain_battery_multi",
                "drone_ids": ["DRONE-01", "DRONE-02"],
                "pct": 12,
                "log": "[TEST EVENT · TICK 8] Severe battery drain injected on DRONE-01 and DRONE-02 (dropped to 12%).",
            },
        ],
        "checkpoints": [
            {"id": "cp1", "label": "4 drones deployed under Rain conditions (2.0x energy drain)", "min_tick": 1},
            {"id": "cp2", "label": "Emergency battery depletion injected on DRONE-01 & DRONE-02 at Tick 8", "min_tick": 8},
            {"id": "cp3", "label": "Drones detect low battery threshold (<25%) and divert toward chargers", "min_tick": 9},
            {"id": "cp4", "label": "Charging stations reserved without conflict; recharging begins", "min_tick": 14},
            {"id": "cp5", "label": "Batteries restored; drones resume missions and complete deliveries", "min_tick": 32},
        ],
    },

    "test_restricted_corridor": {
        "id": "test_restricted_corridor",
        "title": "Test 4: Restricted Airspace & Bottleneck Conflict Resolution",
        "category": "Collision Avoidance",
        "summary": "Opposing drone trajectories pass through a narrow corridor between restricted zones with zero collisions.",
        "objective": "Verify the two-pass reservation collision avoidance algorithm: drones negotiating a shared 1-cell corridor use priority wait/hover rules and alternate routing to prevent head-on and swap collisions.",
        "conditions": {
            "initial_weather": "Clear (1.0x drain)",
            "fleet_size": 2,
            "hazard": "Restricted airspace boundaries create bottleneck corridor",
            "collision_risk": "Opposing trajectories crossing identical midpoint",
            "requests": 2,
        },
        "seed": 204,
        "scenario_name": "default",
        "initial_weather": "Clear",
        "fleet_size": 2,
        "custom_requests": [
            {"id": "REQ-T4-EAST", "pickup": [2, 10], "destination": [17, 10], "deadline": 60},
            {"id": "REQ-T4-WEST", "pickup": [17, 10], "destination": [2, 10], "deadline": 60},
        ],
        "scheduled_events": [],
        "checkpoints": [
            {"id": "cp1", "label": "DRONE-01 and DRONE-02 launched on opposing east-west trajectories", "min_tick": 1},
            {"id": "cp2", "label": "Drones converge towards central bottleneck", "min_tick": 6},
            {"id": "cp3", "label": "Potential cell reservation / swap collision detected by sensors", "min_tick": 8},
            {"id": "cp4", "label": "Two-pass reservation algorithm resolves conflict: priority hover engaged", "min_tick": 9},
            {"id": "cp5", "label": "Both drones clear the corridor safely with 0 collisions", "min_tick": 22},
        ],
    },

    "test_compound_stress": {
        "id": "test_compound_stress",
        "title": "Test 5: Compound Crisis Stress Test (Storm + Breakdown + Drain)",
        "category": "Multi-Variable Stress Test",
        "summary": "Multi-failure scenario combining severe storm, mid-flight motor failure, and emergency low battery simultaneously.",
        "objective": "Stress-test system robustness under compounded concurrent challenges: storm weather cost escalation (3.0x), one drone hardware failure requiring task handoff, and another drone needing an emergency recharge detour.",
        "conditions": {
            "initial_weather": "Storm (3.0x energy consumption + storm cells)",
            "fleet_size": 4,
            "compound_faults": "DRONE-01 breaks down at Tick 8; DRONE-02 drained to 14% at Tick 10",
            "requests": 4,
        },
        "seed": 333,
        "scenario_name": "storm_stress",
        "initial_weather": "Storm",
        "fleet_size": 4,
        "custom_requests": [
            {"id": "REQ-T5-01", "pickup": [1, 2], "destination": [17, 17], "deadline": 100},
            {"id": "REQ-T5-02", "pickup": [15, 2], "destination": [2, 15], "deadline": 100},
            {"id": "REQ-T5-03", "pickup": [8, 14], "destination": [14, 5], "deadline": 100},
            {"id": "REQ-T5-04", "pickup": [3, 16], "destination": [16, 2], "deadline": 100},
        ],
        "scheduled_events": [
            {
                "tick": 8,
                "action": "breakdown",
                "drone_id": "DRONE-01",
                "log": "[TEST EVENT · TICK 8] Motor failure injected on DRONE-01. Drone halted; task returned to pool.",
            },
            {
                "tick": 10,
                "action": "drain_battery",
                "drone_id": "DRONE-02",
                "pct": 14,
                "log": "[TEST EVENT · TICK 10] Critical battery drop (14%) injected on DRONE-02. Initiating charging detour.",
            },
        ],
        "checkpoints": [
            {"id": "cp1", "label": "Fleet dispatches under severe storm conditions (3.0x energy rate)", "min_tick": 1},
            {"id": "cp2", "label": "DRONE-01 suffers mechanical breakdown at Tick 8", "min_tick": 8},
            {"id": "cp3", "label": "DRONE-02 battery drained to 14% at Tick 10 and detours to charger", "min_tick": 10},
            {"id": "cp4", "label": "Active fleet autonomously redistributes orphaned task and charges safely", "min_tick": 14},
            {"id": "cp5", "label": "All surviving operations concluded successfully with 0 collisions", "min_tick": 38},
        ],
    },
}
