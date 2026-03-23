# FW-025 Total-Return Governed Family Integration

Status: `done`

## Goal

Promote the managed EODHD total-return dataset from a side-path config into a first-class governed research family so the supervisor queue can evaluate the cleaner data contract explicitly.

## Dependency Chain

- `FW-024` added EODHD-managed reference and corporate-action ingestion plus the total-return config.
- `FW-025` wires that config into the governed family/program/runbook system as an approved standby family.

## Exit Criteria

- an approved research-family proposal exists for the managed total-return starter branch
- matching director and research-program artifacts exist in repo config
- the supervisor runbook includes the new total-return family as an enabled standby queue item
- regression tests load the new proposal and program definitions
- queue and family summaries still build cleanly with the new standby family in place

## Commit Boundaries

1. total-return family proposal/program/director artifacts and runbook wiring
2. regression tests for proposal/program loading
3. workflow board and hotspot updates
