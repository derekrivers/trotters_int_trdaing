# FW-009 Plan

## Implementation Steps

1. Add a small promotion-path summary layer that can resolve the leading candidate and normalize progression records.
2. Persist the candidate progression summary under `runtime/catalog`.
3. Expose the new summary through the API and reuse it in the dashboard.
4. Add targeted tests for partial-history tolerance, blocking reasons, and stable leading-candidate resolution.

## Chosen Interfaces

- `candidate_progression_summary`
- `current_best_candidate` resolved via the same summary logic
- persisted summary artifacts under `runtime/catalog/promotion_path`

## Acceptance Criteria

- the same leading candidate appears in API and dashboard
- progression records include recommendation state, blocking reasons, and artifact refs
- missing historical details degrade gracefully into a partial but valid summary

## Rollout / Check Order

1. unit tests
2. dashboard/API rendering tests
3. live authenticated dashboard/API check
