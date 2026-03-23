# FW-014 Summary

## Goal

Make the live runtime tell the truth about the active research branch and prevent a director from launching the same queue entry twice under concurrent stepping.

## Status

`done`

## Dependency Chain

- depends on `FW-006` because supervisor continuation and queue stepping already rely on director plan state
- depends on `FW-010` and `FW-013` because the dashboard and API now act as the primary operator truth surfaces

## Exit Criteria

- a director queue entry cannot start duplicate active campaigns because a launch claim now guards the handoff
- the API exposes one compact active-branch summary that explains what is running now
- the dashboard renders the same active-branch summary without forcing the operator to infer state from terminal outcomes
- duplicate active campaigns or director/campaign mismatches surface as explicit warnings instead of silent drift

## Commit Boundaries

1. launch-claim hardening, active-branch summary contract, and regression coverage
2. workflow documentation and board/hotspot sync
