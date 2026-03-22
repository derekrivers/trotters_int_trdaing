# Program Board

| ID | Title | Status | Dependency | Exit Criteria | Next Action |
| --- | --- | --- | --- | --- | --- |
| `FW-001` | Docs and planning sync | `done` | none | workflow system created, roadmap/tasklist synced, stale doc references removed, remaining workflows seeded | use this as the baseline for future workflow creation |
| `FW-002` | Candidate handoff and dashboard | `done` | `FW-001` | dashboard/API show current best candidate, recommendation state, progression history, and next action clearly | use the new `current_best_candidate` contract as the handoff baseline for paper-trading rehearsal work |
| `FW-003` | Paper-trading rehearsal core | `done` | `FW-002` | persisted paper portfolio state, daily runner, operator decision log, and hard blocking rules exist | use the blocked/ready paper rehearsal contract as the baseline for trust hardening and any future paper-day automation |
| `FW-004` | OpenClaw trust hardening | `ready` | `FW-001` | repeated incidents are cooldown-limited, overnight drills are broader, plugin trust config is explicit, and summary quality is tighter | tighten supervisor trust drills and repeated degraded-cycle handling without adding new always-on agents |
| `FW-005` | Risk-sector promotion program | `ready` | `FW-001` | strongest `risk + sector` branch is either promoted under the current policy or explicitly retired with evidence | lock the named seed stack and the stop conditions for the active research branch |

## Ordering Notes

1. `FW-002` should land before `FW-003` because paper-trading rehearsal needs a clearer operator handoff surface.
2. `FW-004` can run in parallel with `FW-002` if the write scopes stay separate.
3. `FW-005` is a standing research track and should keep its evidence current while the product/runtime work proceeds.
