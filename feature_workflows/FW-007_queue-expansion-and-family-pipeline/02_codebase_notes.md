# Codebase Notes

## Primary Files

1. `configs/openclaw/trotters-runbook.json`
2. `configs/directors/refine_seed_continuation.json`
3. `configs/research_programs/refine_seed_continuation.json`
4. `extensions/openclaw/trotters-runtime/index.test.js`
5. `context/14_delivery_roadmap.md`

## Invariants

- every enabled queue item must point to a real director plan file
- every queued family should also have a research-program definition that explains why it exists and how it stops
- queue order matters because the supervisor advances linearly from `current_plan_id`
- the mean-reversion family remains documented but not approved for queue use

## Known Risks

- queue growth can create the illusion of strategic progress if weak fallback families are treated as top-conviction work
- tests can pass while the live runtime still points at the wrong queue file if the gateway is not reading the updated state
- the active beta-defensive branch must not be interrupted just to verify the expanded backlog
