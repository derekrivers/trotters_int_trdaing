# Paper-Trading Preparation Guide

## Purpose

This document defines the boundary between:

1. what the repo already does today
2. what a safe paper-trading phase would require next
3. what should stay deferred until a later live-trading phase

The intent is to stop a promoted strategy from jumping straight from research into real-money operation.

## What Exists Now

The current application can already do these things:

- ingest and validate UK-equity daily-bar data
- run backtests and research sweeps
- rank candidates against validation, holdout, walk-forward, and stress evidence
- operate autonomous campaigns and research directors in the background
- freeze a promoted candidate for human review
- surface the result in the dashboard with handoff pages, scorecards, and notifications

This means the repo is already capable of producing a research-grade candidate and explaining why it was selected.

It does **not** yet place orders, connect to a broker, track a live account, or monitor real-time market state.

## What Paper Trading Means Here

For this project, paper trading should mean:

- one promoted strategy is selected for operational rehearsal
- the strategy produces a daily decision package from the latest available data
- the system records what it *would* hold, buy, sell, or rebalance
- no broker order is sent
- no cash is committed
- all outputs are auditable and reviewable by a human

Paper trading is therefore an operational simulation layer, not a research rerun and not a live execution layer.

## The Next Build Boundary

The next stage after promotion should add four capabilities:

1. **Daily decision export**
   - target holdings
   - rebalance actions
   - expected turnover
   - warnings for stale or missing inputs

2. **Paper portfolio state**
   - current simulated holdings
   - simulated cash
   - last rebalance date
   - simulated fills based on the existing execution model

3. **Operational checks**
   - missing prices
   - stale canonical data
   - missing instrument metadata
   - names that fail liquidity or participation assumptions on the day

4. **Operator review flow**
   - inspect the proposed daily actions
   - confirm whether the day is valid for paper execution
   - record acceptance, skip, or override reasons

## Operator Checklist After A Strategy Is Promoted

Before any promoted candidate moves into paper trading, the operator should review:

### Research Evidence

- validation result and exact benchmark-relative excess return
- holdout result and exact benchmark-relative excess return
- walk-forward pass count
- stress-pack outcome and failure modes
- whether the candidate won by a clear margin or only narrowly

### Operability

- rebalance cadence
- expected turnover
- basket size
- sector and industry concentration behavior
- liquidity and participation assumptions
- whether the result depends on fragile deployment timing

### Data Readiness

- canonical dataset freshness
- feature-set freshness
- universe file version
- benchmark metadata availability
- whether any required data is still being patched manually

### Decision Boundary

The candidate should end this review in one of three states:

- `paper_trade_next`
- `needs_more_research`
- `reject`

Only `paper_trade_next` should move forward.

## What A Daily Paper-Trade Package Should Contain

The daily package should be simple enough for a non-specialist operator to read.

Minimum contents:

- date of decision
- strategy/profile name
- latest data date used
- current simulated holdings
- target holdings
- adds
- trims
- exits
- expected turnover
- gross exposure target
- warnings and blocked actions

It should also include a plain-English summary such as:

> "No action today"  
> "Light rebalance; 2 trims and 1 add"  
> "Blocked due to stale input data"

## Architecture Direction For Paper Trading

The likely next architecture shape is:

- existing research runtime remains unchanged for research
- a separate paper-trading runner consumes one frozen promoted profile
- paper state is persisted separately from research state
- daily decision artifacts are written to a dedicated paper-trading output directory
- the dashboard gains a paper-trading page later, but this is not required to start the phase

Important separation rule:

- research campaigns search for strategies
- paper trading rehearses one already-selected strategy

Those two concerns should remain separate in code and in persisted state.

## What Must Still Be Out Of Scope

The following should remain out of scope during the paper-trading phase:

- broker API integration
- order routing
- live account synchronization
- intraday execution
- automated order submission
- unattended real-money deployment

If any of those become necessary, that is no longer a paper-trading step. It is a new live-execution phase.

## What Live Trading Would Require Later

Only after a stable paper-trading period should the repo consider adding:

- broker adapter and credential handling
- account and position reconciliation
- order lifecycle tracking
- retry, rejection, and partial-fill handling against a real venue
- market-hours awareness and holiday controls
- operational alerting beyond dashboard polling
- capital limits, kill switches, and manual override controls
- audit logging suitable for real-money operation

That later phase should be treated as a separate delivery milestone, not a small extension of research.

## Recommended Next Action

The next implementation step after this document is:

1. add simulated daily decision export for one promoted strategy
2. add a lightweight paper portfolio state model
3. add operator-facing warnings for stale or missing data
4. review whether the resulting output is understandable without reading source code

That is the correct bridge from autonomous research into safe operational rehearsal.
