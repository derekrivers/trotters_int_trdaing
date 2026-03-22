# FW-003 Paper-Trading Rehearsal Core

## Goal

- turn paper trading from a one-off decision artifact into a stateful rehearsal layer with explicit operator actions and hard blocking

## Status

- `done`

## Dependency Chain

- `FW-002`

## Exit Criteria

- separate paper portfolio state exists
- one daily paper runner exists for a frozen promoted profile
- operator actions are logged as `accepted`, `skipped`, `overridden`, or `blocked`
- stale or missing critical inputs can hard-block a paper day explicitly

## Commit Boundaries

- one commit for paper state and daily runner
- one commit for operator action logging and surfaces if the change set is large

## Delivered

- added a separate `paper_rehearsal.py` state layer under `catalog_output_dir / paper_trading`
- added a `paper-trade-runner` CLI command that resolves the promoted candidate or records an explicit blocked paper day
- added a `paper-trade-action` CLI command that records `accepted`, `skipped`, or `overridden` operator decisions and updates paper portfolio state on acceptance
- exposed paper rehearsal state through the API and dashboard overview
- kept research artifacts immutable by storing rehearsal state and day records outside the research runtime database
