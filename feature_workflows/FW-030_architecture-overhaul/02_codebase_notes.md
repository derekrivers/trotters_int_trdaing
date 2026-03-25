# Codebase Notes

## Touched Areas

- `src/trotters_trader/runtime_db.py`
- `src/trotters_trader/research_runtime.py`
- `src/trotters_trader/cli.py`
- `docker-compose.yml`
- `scripts/start-runtime.ps1`
- `scripts/openclaw/start-openclaw.sh`
- `pyproject.toml`
- `tests/test_runtime_db.py`
- `tests/test_research_runtime.py`
- `context/22_tech_stack_and_runtime_brief.md`
- `context/14_delivery_roadmap.md`

## Invariants

- campaign, director, job, artifact, notification, and overview contracts stay backward-compatible at the API and dashboard surface
- runtime catalogs, agent summaries, promotion-path artifacts, and paper-trading state remain filesystem-backed in this workflow
- SQLite remains a supported default for the live stack and for isolated tests when no runtime DB URL is set
- Postgres is an explicit opt-in backend via `TROTTERS_RUNTIME_DATABASE_URL`, the Compose `postgres` profile, or the updated startup helper

## Known Smells

- `research_runtime.py` still owns too many responsibilities even after moving DB compatibility into a dedicated runtime DB module
- runtime exports, notifications, and catalog materialization are still tied tightly to local filesystem semantics
- API and dashboard still run on stdlib WSGI servers, which remains a future operability ceiling after the DB seam lands

## Regression Zones

- runtime initialization and schema migration during mixed worker/coordinator startup
- write-transaction behavior for job leasing, campaign updates, and director progression under the new backend
- staged rollout behavior when Compose services stay on SQLite by default but individual commands or stacks opt into Postgres
- OpenClaw bootstrap behavior when the plugin installer does not materialize the target extension directory before permissions are normalized

## Inspect First

1. `src/trotters_trader/runtime_db.py`
2. `src/trotters_trader/research_runtime.py`
3. `docker-compose.yml`
4. `scripts/start-runtime.ps1`
5. `context/22_tech_stack_and_runtime_brief.md`