# FW-011 Context

## Operator Problem

The rehearsal system could say "blocked", but it did not expose a dedicated decision artifact that clearly separated promotion readiness from the later mechanics of running a paper day.

## Stable References

- `context/16_paper_trading_status.md`
- `feature_workflows/FW-003_paper-trading-rehearsal-core`
- `feature_workflows/FW-009_candidate-progression-ledger`

## Current Behavior At Start

- the paper runner already maintained daily state and operator action logs
- blocked behavior existed for missing promoted candidates
- but the decision boundary was still embedded in runner logic rather than first-class and inspectable

## Non-Goals

- no broker integration
- no live trading
- no new execution model beyond the existing rehearsal runner
