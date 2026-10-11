# Assumptions & Interpretations

This document tracks any design assumptions or clarifications made during implementation where the specification leaves room for interpretation.

| Date | Topic | Assumption / Decision | Rationale |
|---|---|---|---|
| Step 0 | Spec fidelity | Initialized assumptions log. No deviations from spec. | Ground rule: Never deviate from spec silently; choose simplest reading and record here. |
| Step 2 | Restricted cells | Passable in Clear/Windy (+1.0 surcharge); impassable in Rain/Storm. | Weather-dependent traversability per spec rules. |
| Step 2 | Dynamic fleet | Auto-generate start positions near charging stations if user requests N > start_locations. | Ground rule: Any integer N >= 1 is valid, limited only by grid capacity. |
| Step 3 | Storm cell selection | Storm cells dynamically sampled avoiding chargers and start locations. | Drones cannot be blocked from charging or spawning. |
| Step 3 | Partial observability | Weather transitions are computed tick-by-tick on the fly with no lookahead. | Strictly preserves Partially Observable environment property. |
| Step 4 | Heuristic admissibility | Manhattan distance assumes unit base move cost 1.0; weather penalties only increase edge weights. | Ensures h(n) <= c*(n, goal), proving admissibility and optimality of A*. |
| Step 4 | Priority queue ordering | Tuples stored as (f_score, counter, node) with integer counter. | Prevents coordinate comparison failures and ensures deterministic tie-breaking. |
| Step 5 | Battery safety buffer | Detour triggered if battery cannot cover remaining route + target-to-charger + 10 unit buffer. | Avoids stranding drones in remote cells. |
| Step 5 | Task resumption | Drones recharge to 100% then resume GOING_TO_PICKUP or DELIVERING. | Guarantees task delivery completion following charge detours. |
| Step 6 | Multi-attribute scoring | Weighted utility model: distance (0.35), battery (0.25), workload (0.25), availability (0.15). | Shares workload fairly while selecting closest and healthiest drones. |
| Step 6 | Manager-Drone boundary | Delivery Manager strictly assigns tasks and never controls movement or alters drone positions. | Maintains clear agent boundaries per PEAS specification. |
