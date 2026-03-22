# Plan

## Implementation Steps

1. create `feature_workflows/` with a program board, hotspot register, templates, and an archive rule
2. seed the next workflow folders so future work starts with the right context shape
3. sync phase-level docs so they point at workflows instead of keeping stale duplicate tasklists
4. fix top-level README references to current stable docs and the new workflow layer

## Interface Changes

- `feature_workflows/` becomes the maintained interface for active feature planning
- `context/15_phase10_tasklist.md` becomes a phase-level index rather than the detailed source of truth for every pending step

## Acceptance Criteria

- someone can find the stable docs in `context/` and the active work in `feature_workflows/` without guessing
- the next four workflows already have concrete context, code notes, plan, verification, and lessons files

## Rollout And Check Order

1. create the new folder structure
2. update the synced docs
3. run stale-reference searches
4. run live app smoke checks to confirm nothing operational drifted during the docs pass
