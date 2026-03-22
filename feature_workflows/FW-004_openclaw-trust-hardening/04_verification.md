# Verification

## Repo Checks

- `node extensions/openclaw/trotters-runtime/index.test.js`
- targeted Python tests for ops bridge and supervisor integration

## App Checks

- `docker compose ps`
- dashboard/API surfaces for summaries and dispatch telemetry still render

## OpenClaw Checks

- `docker compose exec openclaw-gateway openclaw skills info runtime-supervisor`
- `docker compose exec openclaw-gateway openclaw skills info research-triage`
- inspect gateway logs for plugin trust/config warnings after restart if config changes

## Expected Signals

- repeated incidents are suppressed or cooled down deterministically
- plugin and skills still resolve in the running gateway
- supervisor drill coverage extends beyond the current basic scenarios
