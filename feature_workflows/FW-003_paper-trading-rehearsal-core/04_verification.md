# Verification

## Repo Checks

- `$env:PYTHONPATH='src'; python -m unittest tests.test_reports tests.test_paper_rehearsal tests.test_cli tests.test_api tests.test_dashboard -v`

## App Checks

- `docker compose up --build -d`
- `docker compose up -d --scale worker=4`
- `docker compose ps`
- run `$env:PYTHONPATH='src'; python -m trotters_trader.cli paper-trade-runner --catalog-output-dir runtime/catalog --reference-date 2026-03-22`
- fetch `http://localhost:8890/api/v1/paper-trading/status` with auth and confirm the blocked paper day is visible
- fetch `http://localhost:8888/` and confirm the `Paper Rehearsal` panel shows the same state

## OpenClaw Checks

- not required for this workflow because no OpenClaw plugin or specialist-agent contract changed

## Expected Signals

- blocked paper days are explicit and auditable
- operator decisions are persisted instead of implied
- paper-trading rehearsal stays separate from live execution concerns

## Recorded Results

- repo tests passed: `71` tests across `tests.test_reports`, `tests.test_paper_rehearsal`, `tests.test_cli`, `tests.test_api`, and `tests.test_dashboard`
- live paper runner returned `status: blocked` with `block_code: no_promoted_candidate`
- live paper state now records a system `blocked` action and an uninitialized rehearsal portfolio
- live dashboard returned `200` and showed the `Paper Rehearsal` panel plus the block reason
- live API paper status route returned `blocked` and matched the dashboard state
- rebuild again collapsed the worker pool to one replica, so the verification path explicitly restored `--scale worker=4`
