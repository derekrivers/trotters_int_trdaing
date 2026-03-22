# Verification

## Repo Checks

- `node extensions/openclaw/trotters-runtime/index.test.js`
- `$env:PYTHONPATH='src'; python -m unittest tests.test_openclaw_supervisor_integration tests.test_ops_bridge -v`

## App Checks

- `docker compose ps`
- `Invoke-WebRequest -UseBasicParsing -Uri 'http://localhost:8888/'`
- `Invoke-RestMethod -Uri 'http://localhost:8890/api/v1/runtime/overview' -Headers @{ Authorization = 'Bearer ' + $token }`

## OpenClaw Checks

- `docker compose restart openclaw-gateway`
- `docker compose exec openclaw-gateway openclaw skills info runtime-supervisor`
- `docker compose exec openclaw-gateway openclaw skills info research-triage`
- `docker compose exec openclaw-gateway openclaw plugins list`
- inspect `runtime/openclaw/openclaw.json` after restart to confirm trusted plugin config persisted

## Observed Result

- repeated degraded incidents are suppressed into `service_health_cooldown` with a stable fingerprint and cooldown timer
- stale exhausted terminal context classifies as `idle_exhausted_stale_context` instead of auto-advancing the runbook
- runtime `openclaw.json` now persists `plugins.allow` plus `plugins.load.paths` for `trotters-runtime`
- the gateway is up, both `runtime-supervisor` and `research-triage` resolve as `Ready`, and the dashboard/API remain healthy
