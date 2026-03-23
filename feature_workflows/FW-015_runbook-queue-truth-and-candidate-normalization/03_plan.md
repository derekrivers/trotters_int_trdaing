# Plan

## Implementation Steps

1. Add a shared runbook-queue summary builder that joins the runbook, active branch, and research-program portfolio.
2. Normalize `current_best_candidate` so the no-candidate and unavailable states are explicit.
3. Stop the progression ledger from materializing fake candidate records when no selected candidate exists.
4. Expose the new queue summary and current-best-candidate route through the API, add a portfolio alias, and render the same truth in the dashboard.
5. Verify the live stack shows queue-alignment warnings and no-candidate status instead of silent blanks.

## Interface Changes

- adds `runbook_queue_summary` to runtime overview payloads
- adds `GET /api/v1/runtime/runbook-queue`
- adds `GET /api/v1/runtime/current-best-candidate`
- adds alias `GET /api/v1/research-programs/portfolio`
- normalizes `current_best_candidate.status` to `available`, `no_selected_candidate`, or `unavailable`

## Acceptance Criteria

- the queue summary explains why enabled entries are blocked or untracked
- the current-best-candidate route returns explicit no-candidate state on active operability work
- the dashboard renders both the queue panel and the normalized candidate status
- promotion-path records are not polluted by no-candidate campaign summaries

## Rollout And Check Order

1. run focused Python tests and `py_compile`
2. restart `research-api` and `dashboard`
3. verify `docker compose ps`
4. verify authenticated API calls to `/api/v1/runtime/runbook-queue` and `/api/v1/runtime/current-best-candidate`
5. verify the dashboard overview renders the new queue panel and candidate status
