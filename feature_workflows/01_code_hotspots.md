# Code Hotspots

This is the repo-wide smell register for active planning.

There are almost no useful `TODO` or `FIXME` markers in the codebase, so the main maintenance signal is structural concentration and mixed responsibility.

## Hotspot Register

| Area | Evidence | Why It Matters | Allowed Cleanup Workflow |
| --- | --- | --- | --- |
| `src/trotters_trader/research_runtime.py` | about `3629` lines, about `103` defs | runtime state, campaign orchestration, director orchestration, notifications, agent dispatch, and now service-heartbeat exports all live together | `FW-003`, `FW-005`, `FW-006`, `FW-008` |
| `src/trotters_trader/dashboard.py` | about `2030` lines, about `71` defs | routing, HTML rendering, formatting, operator view-model shaping, and now auth / CSRF behavior are tightly coupled | `FW-002`, `FW-008` |
| `src/trotters_trader/reports.py` | about `1482` lines | report writing, recommendation logic, paper-trade decisions, and scorecards are mixed together | `FW-002`, `FW-003`, `FW-005`, `FW-006` |
| `src/trotters_trader/experiments.py` | about `1874` lines | experiment definitions and tranche/reporting behavior are concentrated in one module | `FW-005`, `FW-006` |
| `src/trotters_trader/api.py` plus `src/trotters_trader/ops_bridge.py` | auth, audit, mutation policy, and transport concerns are hand-rolled WSGI flows | security posture can drift if request validation and audit rules diverge across the two operator APIs | `FW-008` |
| `extensions/openclaw/trotters-runtime/index.js` | about `58` functions | tool definitions, summary normalization, review-pack building, and supervisor decision shaping are in one file | `FW-004` |
| `configs/openclaw/trotters-runbook.json` plus `configs/directors/*.json` | supervisor continuation depends on queue order and explicit approved plans | autonomous progression stops when the runbook has no next item or a stale branch remains in the queue, and queue growth can become speculative if it skips evidence review | `FW-006`, `FW-007` |
| `docker-compose.yml` plus local env posture | host exposure, healthchecks, restart policy, and worker scale baseline all live in one deployment file | security and fault-tolerance regressions can hide in config drift even when the Python code is correct | `FW-008` |
| `README.md` plus roadmap/tasklist docs | stale references already appeared after doc consolidation | top-level guidance can drift from the implemented state and mislead later work | `FW-001`, `FW-008` |

## Smell Rules

1. Do not create a separate refactor-only program yet.
2. Every cleanup must be justified by a workflow deliverable.
3. When splitting a hotspot, prefer responsibility boundaries over mechanical file-count reduction.
4. Preserve existing behavior first, then improve structure.

## First-Read Priority

When changing the system, inspect these before editing:

1. `context/14_delivery_roadmap.md`
2. `context/16_paper_trading_status.md`
3. `context/18_openclaw_status_and_backlog.md`
4. `context/21_openclaw_agent_guide.md`
5. the owning workflow folder in this directory
