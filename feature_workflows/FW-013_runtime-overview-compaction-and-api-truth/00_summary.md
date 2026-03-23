# FW-013 Summary

## Goal

Keep `/api/v1/runtime/overview` compact and operator-focused now that the app has dedicated endpoints for jobs, campaigns, promotion-path state, and research-program details.

## Status

`done`

## Dependency Chain

- depends on `FW-009` through `FW-012` for the new read-model layer
- builds on `FW-008` because the hardened API is now a primary operator surface

## Exit Criteria

- API overview no longer returns the full raw job, campaign, and director history
- overview still reports live worker, running-job, queued-job, service-heartbeat, and promotion-path state
- live response size is materially smaller while preserving the operator contract

## Commit Boundaries

1. API overview compaction plus regression coverage
2. workflow documentation and board/hotspot sync
