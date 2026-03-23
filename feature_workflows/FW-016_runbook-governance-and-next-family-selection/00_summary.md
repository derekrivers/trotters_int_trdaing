# FW-016 Runbook Governance And Next-Family Selection

Status: `done`

## Goal

Stop the supervisor from treating retired or untracked queue entries as valid continuation targets, and make the governed empty-queue state explicit when no approved research family remains.

## Dependency Chain

- `FW-015` introduced `runbook_queue_summary` and normalized candidate / queue visibility.
- `FW-016` moves that summary from operator-only visibility into the real OpenClaw continuation path.

## Exit Criteria

- untracked queue entries are not considered runnable
- retired queue entries are not left enabled in the live runbook
- `trotters_runbook.next_work_item` reads governed queue state before choosing a branch
- the live runtime shows an explicit `define_next_research_family` state instead of silently restarting stale work

## Commit Boundaries

1. code and config changes for queue governance, OpenClaw runbook selection, and regression coverage
2. workflow and roadmap documentation
