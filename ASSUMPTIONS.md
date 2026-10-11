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
