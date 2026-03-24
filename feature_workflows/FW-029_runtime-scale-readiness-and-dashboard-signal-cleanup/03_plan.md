# Plan

## Implementation Steps

1. reduce runtime hot-path write pressure by unifying worker liveness storage, throttling heartbeats and lease renewals, and adding missing indexes
2. throttle or skip expensive coordinator export work when runtime state and artifacts have not materially changed
3. rebalance the dashboard overview so high-signal operator sections remain first-class while duplicated diagnostics move lower on the page

## Interface Changes

- no public API or dashboard route changes
- runtime worker records gain a first-class `heartbeat_at` field as the source of truth for liveness
- overview layout changes demote noisy sections without removing access to diagnostic data

## Acceptance Criteria

- runtime behavior stays correct while supporting 10-worker verification without recurring escaped lock failures
- overview remains operator-readable under busier runtime conditions and no longer leads with repeated low-signal sections

## Rollout And Check Order

1. land runtime changes and scale-focused tests
2. land dashboard signal cleanup and overview tests
3. run local runtime scale verification at `1`, `4`, `6`, and `10` workers with dashboard/API smoke checks
