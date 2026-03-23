# Context

## Problem

- the dashboard has grown into a dense operator surface, but some typography still reflects an earlier, simpler page layout and now reads too large in places
- raw timestamps with sub-second precision add noise and reduce scan speed when operators are looking for runtime state changes quickly

## Linked Stable Docs

- `context/11_architecture_principles.md`
- `context/21_openclaw_agent_guide.md`

## Current Behavior

- overview/detail pages mix large metric text, uppercase section labels, and dense tables in a way that can feel visually unbalanced
- several operator-facing timestamps render with microseconds even though second-level precision is enough for this UI

## Non-Goals

- no runtime orchestration or queue-governance behavior changes
- no redesign of the shared runtime read model unless a tiny formatting helper extraction is clearly justified
