# FW-009 Summary

## Goal

Add a persisted candidate-progression ledger so the app can explain where each candidate family sits on the promotion path without scraping many raw artifacts at read time.

## Status

`done`

## Dependency Chain

- depends on `FW-002` for the current-best-candidate operator contract
- depends on `FW-005` and `FW-007` for program-aware candidate and queue context
- feeds `FW-010`, `FW-011`, and `FW-012`

## Exit Criteria

- candidate progression summaries are materialized under `runtime/catalog`
- recommendation state and blocking reasons come from persisted evidence
- API exposes candidate progression directly as a read model
- the leading candidate resolves from the same summary contract used by the dashboard

## Commit Boundaries

1. promotion-path summary module plus API/dashboard integration
2. workflow documentation and operator-surface sync
