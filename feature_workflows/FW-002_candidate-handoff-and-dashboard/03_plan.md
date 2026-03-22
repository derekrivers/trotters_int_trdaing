# Plan

## Implementation Steps

1. define one operator-facing summary contract for the current best candidate, recommendation state, evidence snapshot, and next action
2. expose that contract through the API before relying on dashboard-only logic
3. refactor `dashboard.py` only as needed to separate page composition from formatting/view-model helpers
4. render the best-candidate summary prominently on the overview and candidate surfaces
5. link the rendered summary back to the persisted scorecard/comparison artifacts

## Interface Changes

- add a compact API surface for current-best-candidate state
- add clearer dashboard sections for recommendation, strengths, weaknesses, and next action

## Acceptance Criteria

- an operator can identify the best current candidate without opening raw JSON
- the dashboard explains why the candidate is not yet paper-trade ready when that is the outcome
- existing handoff artifacts stay linked and inspectable

## Rollout And Check Order

1. shape the API payload
2. update dashboard rendering
3. split `dashboard.py` if the feature made that worthwhile
4. run dashboard/API/report tests
5. verify the live dashboard and API responses
