# Program Board

| ID | Title | Status | Dependency | Exit Criteria | Next Action |
| --- | --- | --- | --- | --- | --- |
| `FW-001` | Docs and planning sync | `done` | none | workflow system created, roadmap/tasklist synced, stale doc references removed, remaining workflows seeded | use this as the baseline for future workflow creation |
| `FW-002` | Candidate handoff and dashboard | `done` | `FW-001` | dashboard/API show current best candidate, recommendation state, progression history, and next action clearly | use the new `current_best_candidate` contract as the handoff baseline for paper-trading rehearsal work |
| `FW-003` | Paper-trading rehearsal core | `done` | `FW-002` | persisted paper portfolio state, daily runner, operator decision log, and hard blocking rules exist | use the blocked/ready paper rehearsal contract as the baseline for trust hardening and any future paper-day automation |
| `FW-004` | OpenClaw trust hardening | `done` | `FW-001` | repeated incidents are cooldown-limited, overnight drills are broader, plugin trust config is explicit, and summary quality is tighter | use the hardened supervisor decision contract and trusted plugin bootstrap as the baseline for future OpenClaw work |
| `FW-005` | Risk-sector promotion program | `done` | `FW-001` | strongest `risk + sector` branch is either promoted under the current policy or explicitly retired with evidence | use the retired branch artifact as the baseline for selecting the next research family instead of re-opening the same path |
| `FW-006` | Next research family and supervisor continuation | `done` | `FW-005` | a new research family is defined, encoded as an approved director plan/runbook item, and the OpenClaw supervisor can auto-advance into it after idle exhaustion | use the beta-defensive branch and `current_plan_id` continuation path as the baseline for the next research-family workflow |

## Ordering Notes

1. `FW-002` should land before `FW-003` because paper-trading rehearsal needs a clearer operator handoff surface.
2. `FW-004` can run in parallel with `FW-002` if the write scopes stay separate.
3. `FW-005` is a standing research track and should keep its evidence current while the product/runtime work proceeds.
4. `FW-006` should start from the retired-branch evidence in `FW-005` rather than reusing stale assumptions about the old `risk + sector` family.
