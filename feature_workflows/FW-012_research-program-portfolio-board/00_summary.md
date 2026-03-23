# FW-012 Summary

## Goal

Create a compact research-program portfolio view so operators can see active, retired, and queue-eligible branches without reconstructing branch history from scattered notes and artifacts.

## Status

`done`

## Dependency Chain

- depends on `FW-005` and `FW-007` for research-program definitions and queue structure
- depends on `FW-009` for shared promotion-path artifact persistence

## Exit Criteria

- a persisted `research_program_portfolio` artifact exists
- API exposes the portfolio directly
- dashboard renders the portfolio alongside active runtime and promotion-path state
- runbook eligibility and fallback intent are visible to the operator

## Commit Boundaries

1. portfolio summary building plus API/dashboard integration
2. workflow documentation and operator-surface sync
