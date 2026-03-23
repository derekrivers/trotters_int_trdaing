# Verification

Repo checks run:

- `node extensions/openclaw/trotters-runtime/index.test.js`
- `$env:PYTHONPATH='src'; python -m unittest tests.test_research_families tests.test_runbook_queue tests.test_api tests.test_dashboard tests.test_cli tests.test_catalog tests.test_promotion_path -v`

Live checks run:

- `docker compose restart research-api dashboard`
- `docker compose restart openclaw-gateway`
- `docker compose ps`
- authenticated `GET /api/v1/runtime/overview`
- authenticated `GET /api/v1/runtime/next-family-status`
- authenticated dashboard `GET /`
- `docker compose exec openclaw-gateway openclaw skills info runtime-supervisor`

Expected result:

- runtime overview remains healthy
- next-family status explains active or governed blocked state explicitly
- dashboard and OpenClaw show the same governed interpretation