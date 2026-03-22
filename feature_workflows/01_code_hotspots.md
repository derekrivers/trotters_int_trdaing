# Code Hotspots

This is the repo-wide smell register for active planning.

There are almost no useful `TODO` or `FIXME` markers in the codebase, so the main maintenance signal is structural concentration and mixed responsibility.

## Hotspot Register

| Area | Evidence | Why It Matters | Allowed Cleanup Workflow |
| --- | --- | --- | --- |
| `src/trotters_trader/research_runtime.py` | about `3629` lines, about `103` defs | runtime state, campaign orchestration, director orchestration, notifications, and agent dispatch all live together | `FW-003`, `FW-005` |
| `src/trotters_trader/dashboard.py` | about `2030` lines, about `71` defs | routing, HTML rendering, formatting, and operator view-model shaping are tightly coupled | `FW-002` |
| `src/trotters_trader/reports.py` | about `1482` lines | report writing, recommendation logic, paper-trade decisions, and scorecards are mixed together | `FW-002`, `FW-003`, `FW-005` |
| `src/trotters_trader/experiments.py` | about `1874` lines | experiment definitions and tranche/reporting behavior are concentrated in one module | `FW-005` |
| `extensions/openclaw/trotters-runtime/index.js` | about `58` functions | tool definitions, summary normalization, review-pack building, and supervisor decision shaping are in one file | `FW-004` |
| `README.md` plus roadmap/tasklist docs | stale references already appeared after doc consolidation | top-level guidance can drift from the implemented state and mislead later work | `FW-001` |

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
