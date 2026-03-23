# FW-006 Next Research Family And Supervisor Continuation

## Goal

- select the next research family after the retired `risk + sector` branch, encode it as repo-managed director/runbook state, and restore automatic supervisor progression

## Status

- `done`

## Dependency Chain

- `FW-005`

## Exit Criteria

- the replacement research family is chosen from current repo-backed evidence rather than guesswork: `beta_defensive_continuation` backed by `momentum_broad_candidate_beta_defensive_n4_ms002_rf63`
- the new family has a named director plan, seed stack, stop conditions, and artifact expectations
- the OpenClaw supervisor runbook contains the next approved item after the retired branch and the supervisor summary carries `current_plan_id` forward from the exhausted director
- an idle exhausted runtime can auto-advance into the new family without manual intervention, and the live runtime has been resumed on that branch

## Commit Boundaries

- keep research-family selection and evidence definition separate from any supervisor/runbook wiring when practical
- if runtime code changes are required, keep them separate from pure config/workflow changes
