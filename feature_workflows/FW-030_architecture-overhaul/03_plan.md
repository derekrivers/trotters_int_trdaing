# Plan

## Implementation Steps

1. introduce a small runtime DB compatibility layer that can connect to SQLite or Postgres and translate the runtime's existing SQL calling pattern safely
2. move runtime-path configuration to a backend-aware model so CLI commands, disposable stacks, and future service rollouts can target Postgres without rewriting the runtime contract
3. wire Compose and the startup helper for an explicit Postgres opt-in path while keeping SQLite as the safe default until a dedicated migration workflow lands
4. verify the new seam with focused unit coverage, full containerized regressions, and disposable Postgres-backed live checks

## Interface Changes

- new runtime DB configuration path via `TROTTERS_RUNTIME_DATABASE_URL`
- new CLI flag `--runtime-database-url` for explicit non-default runtime DB targeting
- new Compose `postgres` profile and `runtime-db` service for local Postgres-backed verification or opt-in stack startup
- updated `scripts/start-runtime.ps1` support for `-UsePostgres` or `-RuntimeDatabaseUrl`
- runtime status keeps the existing `database_path` field name for compatibility, but it can now surface a redacted Postgres target string instead of only a SQLite filesystem path

## Acceptance Criteria

- the runtime can initialize, submit jobs, and report status against Postgres without SQL placeholder or schema errors
- existing SQLite-backed unit and containerized tests continue to pass
- architecture docs clearly state that Postgres is the chosen next orchestration backend while SQLite remains the live default until a migration workflow exists

## Rollout And Check Order

1. land the runtime DB adapter and keep SQLite regression coverage green
2. add an explicit Postgres startup path and validate it in an isolated Compose project
3. keep the main stack on SQLite by default until live-state migration and rollback rules are designed explicitly
4. update workflow docs and stable architecture docs with the broader staged-overhaul plan