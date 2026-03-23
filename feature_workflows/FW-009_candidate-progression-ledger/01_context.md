# FW-009 Context

## Operator Problem

The app could describe a "current best candidate", but it could not answer the fuller question: what has this candidate already passed, what is still blocking it, and what recommendation state should the operator trust right now.

## Stable References

- `context/13_domain_model.md`
- `context/14_delivery_roadmap.md`
- `context/16_paper_trading_status.md`

## Current Behavior At Start

- candidate history existed across profile reports, campaign summaries, and research-program artifacts
- the dashboard shaped a useful current-best summary, but progression state was not a first-class persisted contract
- later features such as paper-trade entry and portfolio views would otherwise have needed to repeat the same evidence gathering

## Non-Goals

- no new research scoring policy
- no broker or live-order behavior
- no dashboard-only recommendation logic
