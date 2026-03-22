# Plan

## Implementation Steps

1. define clearer incident fingerprints and cooldown rules for repeated degraded cycles
2. extend supervisor drills to repeated degraded-cycle and overnight-idle scenarios
3. make plugin trust configuration explicit in the gateway config if the running build supports it cleanly
4. tighten specialist summary instructions and normalization only where they affect operator decisions
5. verify the changes in static tests, Python integration tests, and the running gateway

## Interface Changes

- clearer cooldown/fingerprint state in supervisor incident summaries or dispatch telemetry
- explicit plugin trust configuration in OpenClaw config/bootstrap

## Acceptance Criteria

- the supervisor does not churn on repeated identical incidents
- trust-related gateway warnings are reduced where repo config can fix them
- operator summaries stay compact but become more decision-ready

## Rollout And Check Order

1. add drill and fingerprint coverage first
2. tighten runtime/plugin behavior
3. verify in the running gateway with skills and cron-related smoke checks
