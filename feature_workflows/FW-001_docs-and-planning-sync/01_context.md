# Context

## Problem

- stable docs had already been cleaned up, but active planning still had no dedicated home
- top-level documentation had drifted from the current doc set and still referenced deleted files
- Phase 10 tracking still duplicated old execution sequencing instead of pointing at the real next workflow set

## Linked Stable Docs

- `context/14_delivery_roadmap.md`
- `context/15_phase10_tasklist.md`
- `context/16_paper_trading_status.md`
- `context/18_openclaw_status_and_backlog.md`
- `context/21_openclaw_agent_guide.md`

## Current Behavior

- `context/` is meant to be stable, but it was still the only obvious place to keep new feature notes
- the repo needed a clearer separation between stable reference and active execution planning
- the implemented platform had moved ahead of some of the written sequencing docs

## Non-Goals

- no runtime behavior changes
- no code refactors outside documentation and planning structure
