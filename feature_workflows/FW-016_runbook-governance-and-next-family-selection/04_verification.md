# Verification

Repo checks run:

- `node extensions/openclaw/trotters-runtime/index.test.js`
- `$env:PYTHONPATH='src'; python -m unittest tests.test_runbook_queue tests.test_api tests.test_dashboard -v`

Live checks run:

- `docker compose restart research-api dashboard`
- `docker compose restart openclaw-gateway`
- `docker compose ps`
- authenticated `GET /api/v1/runtime/runbook-queue`
- authenticated dashboard `GET /`
- `docker compose exec openclaw-gateway openclaw skills info runtime-supervisor`

Expected live result:

- queue summary status `aligned`
- `recommended_action = define_next_research_family`
- no enabled queue items remain
- dashboard renders the same governed empty-queue state
- `runtime-supervisor` skill remains ready after restart
