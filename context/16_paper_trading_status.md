# Paper-Trading Status

## Purpose

Define the current paper-trading boundary for the project, record whether the repo is actually ready to enter that phase, and keep the next required implementation steps in one place.

## Current Decision

As of 2026-03-22, the repo is not yet ready to enter a real paper-trading phase.

Recommendation state:

- `needs_more_research`

Interpretation:

- the platform is now close to paper-trading readiness from an operator and workflow perspective
- the main blocker is still strategy validity, not missing dashboards or missing OpenClaw plumbing
- paper trading should begin only after the research stack freezes a genuinely promotable candidate

## What Already Exists

The repo can already:

- ingest and validate UK-equity daily-bar data
- run autonomous research campaigns and directors
- rank candidates against validation, holdout, walk-forward, and stress evidence
- freeze and explain candidate outcomes in operator-facing artifacts
- generate daily decision-style outputs for review without sending broker orders

That means the system already has most of the research and operator surface needed for paper trading.

## What Paper Trading Means Here

For this project, paper trading should mean:

- one promoted strategy is selected for operational rehearsal
- the strategy produces a daily decision package from the latest available data
- the system records what it would hold, buy, sell, or rebalance
- no broker order is sent
- no cash is committed
- all outputs are auditable and reviewable by a human

Paper trading is therefore an operational rehearsal layer, not another research sweep and not live execution.

## Readiness Checklist

### Research Validity

- promoted strategy exists: fail
- promotion decision is frozen and visible: fail
- validation, holdout, walk-forward, and stress evidence agree on the same candidate: fail
- operator scorecard recommends `paper_trade_next`: fail

### Operator And Handoff Layer

- dashboard explains campaign and strategy state in plain English: pass
- promotion notifications and handoff artifacts exist: pass
- candidate comparison and scorecard outputs exist: pass
- the OpenClaw operator layer can summarize candidate state and paper-trade readiness: pass

### Paper-Trading Boundary

- daily decision package can be generated for one profile: pass
- package includes holdings, rebalance actions, turnover, and warnings: pass
- broker and live-order logic remain out of scope: pass
- separate paper portfolio state exists: fail
- operator accept, skip, or override decision log exists: fail
- hard blocking on stale or missing critical inputs exists: fail

## Main Remaining Gaps

### 1. No Valid Candidate Has Been Promoted

This is still the main blocker. Paper trading should not rehearse a strategy that the repo itself does not yet consider promotion-worthy.

### 2. No Separate Paper Portfolio State

The repo can generate decision outputs, but it does not yet maintain a separate simulated live portfolio with carried holdings, paper cash, last accepted rebalance, and accepted or skipped operator actions.

### 3. No Daily Paper Runner

There is no dedicated runner that:

- loads the frozen promoted strategy
- checks data freshness and blocking conditions
- generates the day package
- persists the result into paper-trading state

### 4. Warnings Exist, But Not Hard Operational Gates

Paper trading needs explicit no-go states for stale or incomplete data. The operator should not have to infer whether a warning is safe to ignore.

### 5. No Operator Decision Log

The system still lacks an auditable log for:

- accepted
- skipped
- overridden
- blocked

## Practical Decision Boundary

The repo should move into a paper-trading build only when all of the following are true at the same time:

1. one strategy is frozen with a true promotion outcome
2. the operator scorecard says `paper_trade_next`
3. the strategy remains acceptable under the defined stress pack
4. a separate paper portfolio state model is implemented
5. stale or incomplete data can block a paper-trading day explicitly

## Recommended Next Implementation Steps

1. keep autonomous research running until a true promoted candidate exists
2. add a separate paper portfolio state model
3. add a daily paper runner for one frozen profile
4. add explicit hard-blocking rules for stale or missing critical data
5. add operator accept, skip, override recording for each paper-trading day

## Out Of Scope For This Phase

The following should remain out of scope during paper trading:

- broker API integration
- live order routing
- account synchronization
- intraday execution
- automated real-money order submission
- unattended live deployment

If any of those become necessary, that is no longer paper trading. It is a later live-execution phase.
