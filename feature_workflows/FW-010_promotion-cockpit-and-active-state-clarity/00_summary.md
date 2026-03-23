# FW-010 Summary

## Goal

Make the main operator view separate live runtime state from historical outcomes and show the promotion path, paper-trade gate, and current best candidate in one coherent cockpit.

## Status

`done`

## Dependency Chain

- depends on `FW-009` for candidate progression data
- builds on `FW-002` and `FW-008` for the authenticated operator console baseline

## Exit Criteria

- active runtime is visually separate from terminal outcomes
- the dashboard shows leading candidate, progression, and paper-trade gate at the top level
- API overview and dashboard agree on the same operator-facing contract

## Commit Boundaries

1. operator-surface view model and rendering updates
2. workflow documentation and naming sync
