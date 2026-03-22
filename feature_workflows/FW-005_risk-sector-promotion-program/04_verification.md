# Verification

## Repo Checks

- `$env:PYTHONPATH='src'; python -m unittest tests.test_research_programs tests.test_cli -v`

## App Checks

- `docker compose ps`
- `Invoke-WebRequest http://localhost:8888/guide`
- `Invoke-WebRequest http://localhost:8890/api/v1/runtime/overview`
- verify runtime overview, campaign state, and latest artifacts remain readable while the branch runs

## OpenClaw Checks

- not required for this workflow because no OpenClaw plugin or skill contracts changed

## Expected Signals

- branch evidence stays current in one place
- promotion or retirement can be justified from persisted artifacts
- no policy thresholds are silently weakened

## Actual Outcome

- `promotion-check` was rerun for `configs/eodhd_momentum_broad_candidate_risk_sector_sec3.toml` with `--output-dir-override runtime/catalog`
- validation remained benchmark-negative at roughly `-3.80%`
- holdout remained benchmark-negative at roughly `-12.92%`
- walk-forward remained `0 / 3` passing windows
- `research-program-report` wrote `runtime/catalog/risk_sector_promotion_program/research_program.json` with status `retired`
