# FW-020 Research-Batch Bootstrap For Approved Family

Status: `done`

## Goal

Provide one bounded bootstrap path from an approved family proposal to runnable plan/program artifacts and queue entry updates.

## Dependency Chain

- `FW-017` defines what can be approved.
- `FW-019` defines what can be queued.
- `FW-020` adds the path that materializes the approved family into runnable artifacts.

## Exit Criteria

- one command/path bootstraps the approved family
- bootstrap writes the director plan, program definition, and queue-aligned artifacts
- the approved family can become active without bespoke manual wiring

## Commit Boundaries

1. bootstrap code/config and regression coverage
2. workflow and roadmap documentation