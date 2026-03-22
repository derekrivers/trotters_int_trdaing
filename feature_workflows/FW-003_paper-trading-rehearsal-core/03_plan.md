# Plan

## Implementation Steps

1. define a persisted paper portfolio state model with holdings, paper cash, last accepted rebalance, and day status
2. define a paper decision log model that captures `accepted`, `skipped`, `overridden`, and `blocked`
3. add a daily runner that loads the frozen promoted profile, validates freshness, and either emits a blocked outcome or a day package
4. surface the current paper day state and last operator action through the API/dashboard
5. extract paper-state logic out of report-writing code only where the feature requires it

## Interface Changes

- new persisted paper-trading state artifact or state directory
- new operator decision log artifact or table
- new CLI entrypoint for the daily paper runner

## Acceptance Criteria

- if no promoted candidate exists, the runner emits a clear blocked state
- if a promoted candidate exists, the runner can generate and persist the day package and state
- operator actions can be recorded and audited later

## Rollout And Check Order

1. define the state and decision schemas
2. add the runner
3. add operator action recording
4. expose the result in operator surfaces
5. run targeted tests and live smoke checks
