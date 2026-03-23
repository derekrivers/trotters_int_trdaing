# Code Hotspots

This is the repo-wide smell register for active planning.

There are almost no useful `TODO` or `FIXME` markers in the codebase, so the main maintenance signal is structural concentration and mixed responsibility.

## Hotspot Register

| Area | Evidence | Why It Matters | Allowed Cleanup Workflow |
| --- | --- | --- | --- |
| `src/trotters_trader/research_runtime.py` | about `3629` lines, about `103` defs | runtime state, campaign orchestration, director orchestration, notifications, agent dispatch, service-heartbeat exports, and now launch-claim recovery all live together | `FW-003`, `FW-005`, `FW-006`, `FW-008`, `FW-014` |
| `src/trotters_trader/dashboard.py` | about `2030` lines, about `71` defs | routing, HTML rendering, formatting, operator view-model shaping, auth / CSRF behavior, and now promotion-path plus active-branch, runbook-queue, next-family, and backlog-continuity panels are tightly coupled | `FW-002`, `FW-008`, `FW-010`, `FW-012`, `FW-014`, `FW-015`, `FW-016`, `FW-018`, `FW-021`, `FW-022`, `FW-023` |
| `src/trotters_trader/reports.py` plus `src/trotters_trader/promotion_path.py` | report writing, recommendation logic, progression shaping, current-best-candidate normalization, paper-trade readiness, and Windows-safe artifact writes are closely related but still spread across a small cluster | `FW-009`, `FW-010`, `FW-011`, `FW-012`, `FW-015`, `FW-016`, `FW-020`, `FW-021` |
| `src/trotters_trader/experiments.py` | about `1874` lines | experiment definitions and tranche/reporting behavior are concentrated in one module | `FW-005`, `FW-006`, `FW-012` |
| `src/trotters_trader/api.py` plus `src/trotters_trader/ops_bridge.py` | auth, audit, mutation policy, transport concerns, promotion-path read surfaces, overview compaction, active-branch visibility, queue governance, and now family-comparison / backlog-continuity summaries all live in hand-rolled WSGI flows | security posture and operator contracts can drift if request validation, payload size, and read-model shaping diverge | `FW-008`, `FW-009`, `FW-011`, `FW-012`, `FW-013`, `FW-014`, `FW-015`, `FW-016`, `FW-018`, `FW-021`, `FW-022`, `FW-023` |
| `src/trotters_trader/active_branch.py` | new summary logic joins director detail, campaign detail, job counts, warnings, and operator messaging | this contract is now the fastest explanation of what is running when no leading candidate exists, so it must stay aligned with runtime truth | `FW-014` |
| `src/trotters_trader/runbook_queue.py` | runbook parsing, portfolio alignment, active-plan drift warnings, queue-level operator messaging, approval-state blockers, and backlog continuity depth live in one summary builder | this contract is now the only compact explanation of whether the supervisor queue is runnable, blocked pending approval, or running out of standby families | `FW-015`, `FW-016`, `FW-019`, `FW-021`, `FW-023` |
| `src/trotters_trader/research_families.py` plus `configs/research_family_proposals/*.json` | proposal validation, approval-state comparison, next-family status, backlog continuity, and bootstrap orchestration now form one governance surface | this is now the approval boundary between research ideas and supervisor queue execution, so status drift or weak validation would reopen unsafe continuation paths or hide a thin standby backlog | `FW-017`, `FW-018`, `FW-019`, `FW-020`, `FW-021`, `FW-023` |
| `src/trotters_trader/paper_rehearsal.py` | runner, state, operator actions, and now gate consumption live together | future paper-day automation could blur the boundary between gate evaluation and rehearsal state if this grows without discipline | `FW-003`, `FW-011` |
| `extensions/openclaw/trotters-runtime/index.js` | about `58` functions | tool definitions, summary normalization, review-pack building, supervisor decision shaping, governed runbook selection, and now next-family blocked/active UX are in one file | `FW-004`, `FW-016`, `FW-019`, `FW-021` |
| `src/trotters_trader/catalog.py` plus `src/trotters_trader/promotion_path.py` | both now carry Windows-safe atomic-write retry paths for live artifact materialization under the running stack | write semantics can regress silently on Windows when live services hold handles, so retry behavior needs direct regression coverage whenever new artifact writers are added | `FW-017`, `FW-020`, `FW-021` |
| `configs/openclaw/trotters-runbook.json` plus `configs/directors/*.json` plus `configs/research_programs/*.json` plus `configs/research_family_proposals/*.json` | supervisor continuation now depends on agreement between proposal approval, program definition, bootstrap materialization, queue enablement, and standby-family backlog depth | if these layers drift, the supervisor can appear blocked, active, or continuity-safe for the wrong reason | `FW-017`, `FW-018`, `FW-019`, `FW-020`, `FW-021`, `FW-023` |
| `docker-compose.yml` plus local env posture | host exposure, healthchecks, restart policy, and worker scale baseline all live in one deployment file | security and fault-tolerance regressions can hide in config drift even when the Python code is correct | `FW-008` |

## Smell Rules

1. Do not create a separate refactor-only program yet.
2. Every cleanup must be tied to a workflow deliverable.
3. When splitting a hotspot, prefer responsibility boundaries over mechanical file-count reduction.
4. Preserve existing behavior first, then improve structure.

## First-Read Priority

When changing the system, inspect these before editing:

1. `context/14_delivery_roadmap.md`
2. `context/16_paper_trading_status.md`
3. `context/18_openclaw_status_and_backlog.md`
4. `context/21_openclaw_agent_guide.md`
5. the owning workflow folder in this directory
