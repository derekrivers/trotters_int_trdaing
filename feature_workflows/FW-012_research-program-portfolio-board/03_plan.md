# FW-012 Plan

## Implementation Steps

1. Walk repo-managed research-program definitions and existing runtime summaries.
2. Enrich each program with runbook eligibility and next-step context.
3. Persist the portfolio as a compact artifact.
4. Expose the portfolio in API and dashboard next to the other promotion-path summaries.

## Chosen Interfaces

- `research_program_portfolio`
- focused API endpoint for the portfolio
- dashboard overview section for program state

## Acceptance Criteria

- active, exhausted, retired, and fallback-ready programs render correctly
- runbook eligibility is visible
- retired branches stay explicitly retired instead of lingering as implied current best

## Rollout / Check Order

1. promotion-path unit tests
2. API/dashboard tests
3. live overview and portfolio endpoint checks
