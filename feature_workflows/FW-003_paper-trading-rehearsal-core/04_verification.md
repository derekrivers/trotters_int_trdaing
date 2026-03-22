# Verification

## Repo Checks

- targeted paper-trade decision tests
- CLI tests for the paper runner
- dashboard/API tests for paper-day status and operator decision visibility

## App Checks

- `docker compose ps`
- run the paper runner against the current repo state and confirm it blocks cleanly if no promoted candidate exists
- confirm dashboard/API show the resulting paper-day status

## OpenClaw Checks

- if paper-readiness summaries change shape, re-check the `paper-trade-readiness` agent surfaces

## Expected Signals

- blocked paper days are explicit and auditable
- operator decisions are persisted instead of implied
- paper-trading rehearsal stays separate from live execution concerns
