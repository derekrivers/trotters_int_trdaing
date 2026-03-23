# Plan

## Implementation Steps

1. review repo-backed evidence and choose the next research family that is materially different from the retired branch
2. define that family as:
   - a research-program config
   - a director plan
   - explicit stop conditions and artifact expectations
3. update the supervisor runbook so the next approved item exists after the old exhausted path
4. verify the supervisor decision path can legally auto-advance into the new item when the runtime next reaches an idle exhausted state
5. update workflow and roadmap context so the repo no longer points operators at the retired branch

## Interface Changes

- add one new approved work item to the OpenClaw supervisor queue
- add one repo-managed research-family definition that explains why this family is next

## Acceptance Criteria

- the next research family can be explained from persisted evidence
- the supervisor has a valid next queue item instead of stopping at an exhausted one
- the resulting runtime behavior is autonomous but still conservative

## Rollout And Check Order

1. choose the next family
2. add its configs
3. wire the runbook
4. verify the supervisor sees the updated queue
5. optionally trigger the first run if the runtime is still idle
