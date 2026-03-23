# FW-013 Context

## Operator Problem

The live runtime was healthy, but `/api/v1/runtime/overview` had grown into a multi-megabyte payload because it still embedded the full job, campaign, and director history. That made the overview route heavier than the operator task required.

## Stable References

- `feature_workflows/FW-009_candidate-progression-ledger`
- `feature_workflows/FW-010_promotion-cockpit-and-active-state-clarity`
- `feature_workflows/FW-012_research-program-portfolio-board`

## Current Behavior At Start

- the API overview carried the new promotion-path summaries
- but it also returned raw runtime status lists for all jobs, campaigns, and directors
- dedicated detail routes already existed, so the overview was duplicating history rather than summarizing current state

## Non-Goals

- no runtime orchestration change
- no dashboard routing rewrite
- no new auth model
