# FW-010 Plan

## Implementation Steps

1. Reuse the shared promotion-path summaries in the dashboard overview payload.
2. Add clearer top-level sections for active runtime, candidate progression, paper-trade gate, and research-program portfolio.
3. Rename terminal-outcome sections so they cannot be mistaken for live state.
4. Extend tests to assert the new sections and naming.

## Chosen Interfaces

- existing `/api/v1/runtime/overview`
- dashboard overview sections driven by the same overview contract

## Acceptance Criteria

- live runtime state is explicit at a glance
- terminal outcomes are labeled as historical
- the dashboard and API show the same current best candidate and next action

## Rollout / Check Order

1. dashboard/API tests
2. authenticated overview render
3. authenticated API overview fetch
