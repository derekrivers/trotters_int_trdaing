# Verification

## Repo Checks

- `docker compose config`
- `$env:PYTHONPATH='src'; python -m unittest tests.test_runtime_db tests.test_research_runtime.ResearchRuntimeTests.test_initialize_runtime_enables_wal_mode tests.test_research_runtime.ResearchRuntimeTests.test_concurrent_initialize_runtime_calls_do_not_fail tests.test_research_runtime.ResearchRuntimeTests.test_initialize_runtime_only_backfills_worker_heartbeat_on_column_migration tests.test_research_runtime.ResearchRuntimeTests.test_heartbeat_worker_retries_transient_database_lock`
- `docker compose -f docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from test-runner`

## App Checks

- `docker compose -p trotters-arch-verify --profile postgres build coordinator`
- `docker compose -p trotters-arch-verify --profile postgres up -d runtime-db`
- create `configs/.tmp_postgres_smoke_spec.json` with `{"job_id":"smoke-job-1","command":"backtest","config_path":"configs/backtest.toml"}`
- `$env:TROTTERS_RUNTIME_DATABASE_URL='postgresql://trotters:...@runtime-db:5432/trotters_runtime'; docker compose -p trotters-arch-verify --profile postgres run --rm coordinator research-submit --runtime-root /runtime/research_runtime --catalog-output-dir /runtime/catalog --spec configs/.tmp_postgres_smoke_spec.json`
- `$env:TROTTERS_RUNTIME_DATABASE_URL='postgresql://trotters:...@runtime-db:5432/trotters_runtime'; docker compose -p trotters-arch-verify --profile postgres run --rm coordinator research-status --runtime-root /runtime/research_runtime --catalog-output-dir /runtime/catalog`
- `docker compose -p trotters-arch-verify --profile postgres down -v`

## Stack Recovery Check

- `docker compose up -d --scale worker=5`
- `Start-Sleep -Seconds 10; docker compose ps`

## OpenClaw Checks

- the full containerized test suite includes `test_openclaw_supervisor_integration`, which caught and then verified the bootstrap-script fallback for missing installed plugin directories

## Expected Signals

- focused unit tests pass with SQLite fallback still active
- the full containerized regression suite passes after the OpenClaw bootstrap fallback fix
- the disposable Postgres-backed runtime initializes cleanly, accepts a queued job, and reports runtime status without `database is locked`, placeholder, or schema errors
- the main stack returns to healthy SQLite-backed service status after the staged rollout shape is restored