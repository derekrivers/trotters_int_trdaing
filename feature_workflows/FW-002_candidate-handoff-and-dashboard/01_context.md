# Context

## Problem

- the repo already has scorecards, handoff pages, summaries, and agent outputs
- but the operator still has to infer the current best candidate by reading across multiple surfaces
- the dashboard is functional, but it does not yet reduce the decision load enough

## Linked Stable Docs

- `context/14_delivery_roadmap.md`
- `context/16_paper_trading_status.md`
- `context/21_openclaw_agent_guide.md`

## Current Behavior

- operator-facing artifacts exist in the catalog
- the dashboard can render handoff and scorecard pages
- the API and dashboard still expose more raw state than final operator judgment

## Non-Goals

- do not change promotion policy
- do not add paper portfolio state in this workflow
- do not add new always-on agents
