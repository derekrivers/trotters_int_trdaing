# Verification

- `$env:PYTHONPATH='src'; python -m unittest tests.test_active_branch tests.test_dashboard tests.test_api tests.test_research_families tests.test_runbook_queue` passed: `65` tests.
- Restarted live `research-api` and `dashboard` with `docker compose restart research-api dashboard`.
- Verified live blocked-idle state from the dashboard container: `next_family_status.status = blocked_pending_approval` and `health.status = blocked` with the retired-family message.
- Verified in-container dashboard health endpoint with `docker compose exec dashboard python -c "from urllib.request import urlopen; print(urlopen('http://127.0.0.1:8888/healthz').read().decode())"` -> `ok`.
- `docker compose ps` shows both `dashboard` and `research-api` as `healthy` after the restart.
