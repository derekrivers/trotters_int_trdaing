# FW-029 Runtime Scale Readiness And Dashboard Signal Cleanup

## Goal

- make the SQLite-backed runtime ready for 10-worker operation while keeping the dashboard overview useful as runtime concurrency and background telemetry increase

## Status

- `done`

## Dependency Chain

- `FW-008`
- `FW-026`
- `FW-028`

## Exit Criteria

- runtime hot-path DB pressure was reduced with first-class worker heartbeats, throttled heartbeats and lease renewals, and export/index cleanup
- a 10-worker local smoke plus 10-worker concurrency regression coverage completed without escaped `database is locked` failures
- the overview page now keeps operator-facing sections first and moves lower-signal diagnostics off the main first-screen narrative

## Commit Boundaries

- workflow scaffolding and planning updates
- runtime throughput and export-throttling changes plus tests
- dashboard overview signal cleanup plus verification and workflow closeout
