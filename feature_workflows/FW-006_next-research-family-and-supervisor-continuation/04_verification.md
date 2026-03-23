# Verification

## Repo Checks

- `node extensions/openclaw/trotters-runtime/index.test.js`
- `$env:PYTHONPATH='src'; python -m unittest tests.test_openclaw_supervisor_integration tests.test_research_programs tests.test_cli -v`
- confirm no stale references still point to the retired `risk + sector` family as the active branch

## App Checks

- `docker compose ps`
- `Invoke-WebRequest http://localhost:8888/guide -UseBasicParsing | Select-Object -ExpandProperty StatusCode`
- `Invoke-WebRequest http://localhost:8888/ -UseBasicParsing` and confirm the page contains `beta-defensive-director` and `beta-defensive-primary`
- verify the runtime still shows no duplicate active directors or campaigns after the next family is started

## OpenClaw Checks

- `docker compose restart openclaw-gateway`
- `docker compose exec openclaw-gateway openclaw skills info runtime-supervisor`
- verify the supervisor sees the updated runbook and can resolve the new next work item when `currentPlanId` is passed from `summary.supervisor_decision.current_plan_id`
- verify the stale-context guard still prevents accidental churn

## Research Program Checks

- `$env:PYTHONPATH='src'; python -m trotters_trader.cli research-program-report --program-file configs/research_programs/beta_defensive_continuation.json --catalog-output-dir runtime/catalog`
- confirm `runtime/catalog/beta_defensive_continuation_program/research_program.json` records the branch as `active` with `recommended_action: run_next_step` before the first run

## Runtime Activation Checks

- start the live branch inside the Compose-backed runtime: `docker compose exec research-api python -m trotters_trader.cli research-director-start --runtime-root /runtime/research_runtime --catalog-output-dir /runtime/catalog --director-plan-file /app/configs/directors/beta_defensive_continuation.json --director-name beta-defensive-director`
- note that host-side CLI commands warn when they target `runtime/research_runtime` instead of the named-volume runtime mounted at `/runtime/research_runtime`; that path should not be used for live verification

## Expected Signals

- a next approved research item exists
- the supervisor no longer stalls simply because the queue ended
- the new branch still respects explicit stop conditions instead of running indefinitely
- the live dashboard shows the new defensive director and campaign active
