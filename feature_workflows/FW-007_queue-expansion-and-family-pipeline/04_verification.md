# Verification

## Repo Checks

- `node extensions/openclaw/trotters-runtime/index.test.js`
- `$env:PYTHONPATH='src'; python -m unittest tests.test_research_programs tests.test_cli -v`
- confirm `configs/openclaw/trotters-runbook.json` now contains three enabled queue items in the intended order

## App Checks

- `docker compose ps`
- `Invoke-WebRequest http://localhost:8888/guide -UseBasicParsing | Select-Object -ExpandProperty StatusCode`
- `Invoke-WebRequest http://localhost:8888/ -UseBasicParsing` and confirm the active beta-defensive branch remains visible

## Expected Signals

- `broad_operability` remains first
- `beta_defensive_continuation` remains second
- `refine_seed_continuation` is third
- the live runtime is still healthy and still running the active beta-defensive branch while the queue expands behind it
