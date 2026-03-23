# Plan

## Implementation Steps

1. Add a shared active-branch summary builder that can explain the live director/campaign pair and emit warnings on duplicate active campaigns.
2. Harden `step_director()` with a durable launch-claim contract so duplicate stepping recovers or waits instead of starting another campaign.
3. Expose the summary through the API and render it in the dashboard overview.
4. Add targeted regressions for launch claims, duplicate-campaign warnings, and dashboard/API visibility.
5. Restart the affected services and verify the live runtime collapses back to one active campaign.

## Interface Changes

- adds a shared `active_branch_summary` contract to runtime overview data
- adds `GET /api/v1/runtime/active-branch`
- persists `launch_in_progress` in director state while a campaign launch is being claimed or recovered

## Acceptance Criteria

- a recent launch claim blocks duplicate launches for the same queue entry
- an existing matching active campaign can be adopted after a partial launch handoff
- API and dashboard agree on the active branch identity and recommended operator action
- duplicate active campaigns show as warnings instead of silently passing as healthy

## Rollout And Check Order

1. run targeted Python tests and `py_compile`
2. restart `research-api`, `research-director`, and `dashboard`
3. verify `docker compose ps`
4. verify authenticated API overview and active-branch endpoints
5. verify the dashboard renders the Active Research Branch section cleanly
