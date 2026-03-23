# FW-015 Summary

## Goal

Make the supervisor runbook, research-program portfolio, and current-best-candidate summary tell one consistent operator story.

## Status

`done`

## Dependency Chain

- depends on `FW-009` and `FW-012` because the promotion-path and research-program read models already exist
- depends on `FW-014` because the active-branch summary is now the runtime truth anchor for supervisor work

## Exit Criteria

- the app exposes one `runbook_queue_summary` that shows active, blocked, untracked, and next-runnable queue items
- the current-best-candidate contract makes `no_selected_candidate` explicit instead of forcing callers to infer it from missing fields
- API and dashboard both expose the new queue truth and normalized candidate state
- the promotion-path ledger no longer treats a no-candidate operability branch as a real candidate record

## Commit Boundaries

1. runbook-queue summary, current-best-candidate normalization, API/dashboard wiring, and regression coverage
2. workflow documentation and board/hotspot sync
