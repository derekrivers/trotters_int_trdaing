# FW-003 Paper-Trading Rehearsal Core

## Goal

- turn paper trading from a one-off decision artifact into a stateful rehearsal layer with explicit operator actions and hard blocking

## Status

- `ready`

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
