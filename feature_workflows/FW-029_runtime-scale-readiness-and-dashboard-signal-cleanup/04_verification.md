# Verification

## Automated Checks

- `$env:PYTHONPATH='src'; python -m unittest tests.test_research_runtime`
- `$env:PYTHONPATH='src'; python -m unittest tests.test_dashboard`

## Local Live Checks

- `docker compose up --build -d`
- `docker compose up -d --scale worker=4`
- `docker compose up -d --scale worker=6`
- `curl.exe --max-time 10 http://127.0.0.1:8888/healthz` returned `ok`
- `curl.exe --max-time 10 http://127.0.0.1:8890/readyz` returned `ready: true` with `6 workers active`
- dashboard and API container logs recorded repeated `GET /` and `GET /api/v1/runtime/overview` `200` responses during scale checks
- worker and coordinator logs did not show recurring `database is locked` markers during the verification window

## 10-Worker Proof

- `$env:PYTHONPATH='src'; python -` local smoke under `runtime/fw029_live_smoke` ran 10 real backtest jobs across 10 workers and finished with `completed_jobs=10`, `failed_jobs=0`, `counts.completed=10`, and `worker_count=10`
- the automated runtime suite also includes a separate 10-worker concurrency regression that exercises the hot path without escaped lock failures

## Notes

- full-body authenticated host reads of `/` and `/api/v1/runtime/overview` remained unreliable through the Windows host-to-Docker path, so live route confirmation used health endpoints plus container access logs rather than a long host-side body download
