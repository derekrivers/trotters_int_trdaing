# FW-023 Approved Backlog Continuity

Status: `done`

## Goal

Keep the governed runtime from halting every time one approved family retires by maintaining a materialized backlog of approved standby families and surfacing backlog depth directly in the queue and family summaries.

## Dependency Chain

- `FW-021` created the governed next-family status.
- `FW-022` aligned blocked-idle health wording with that governed state.
- `FW-023` extends the same governance model with standby-backlog continuity instead of one-family-at-a-time resumption.

## Exit Criteria

- research-family comparison and next-family summaries expose approved standby backlog depth and low-backlog status
- runbook queue summary exposes continuity depth for ready standby items
- the live queue contains multiple fresh approved families with new plan IDs, not re-enabled retired branches
- the runtime can resume on the new queue head while still retaining approved standby families behind it

## Commit Boundaries

1. backlog-aware summary/model changes and regression tests
2. fresh approved family artifacts and runbook continuity wiring
3. workflow and roadmap documentation