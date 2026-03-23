# FW-019 Runbook Approval Gate And Queue Re-Entry

Status: `done`

## Goal

Make runbook eligibility approval-aware so a plan can only become runnable when it maps to an approved research family definition.

## Dependency Chain

- `FW-017` introduced proposals.
- `FW-018` introduced comparison and status contracts.
- `FW-019` connects those contracts to queue governance.

## Exit Criteria

- unapproved families are visible but not runnable
- queue summaries expose approval-state blockers clearly
- OpenClaw runbook selection consumes approval-aware queue summaries

## Commit Boundaries

1. queue-governance code and OpenClaw integration
2. workflow and roadmap documentation