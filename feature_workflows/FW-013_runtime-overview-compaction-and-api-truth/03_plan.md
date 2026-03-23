# FW-013 Plan

## Implementation Steps

1. Keep the full runtime snapshot internal to the controller for health and active-state shaping.
2. Return a compact `status` contract from the API overview with workers, running jobs, queued preview, service heartbeats, and recent terminal items.
3. Add regression coverage that ensures raw history lists are no longer returned from the overview route.
4. Verify live response size and operator counts after restarting `research-api`.

## Chosen Interfaces

- compact `status` object under `/api/v1/runtime/overview`
- existing detail endpoints remain the source for full job/campaign/director history

## Acceptance Criteria

- no raw `jobs`, `campaigns`, or `directors` arrays in API overview `status`
- overview still reports current workers and running jobs
- live response size drops materially from the multi-megabyte range

## Rollout / Check Order

1. targeted API tests
2. restart `research-api`
3. live overview size and field check
4. final Compose health check
