# Verification

Repo checks run:

- `node extensions/openclaw/trotters-runtime/index.test.js`
- `$env:PYTHONPATH='src'; python -m unittest tests.test_runbook_queue tests.test_api -v`

Expected result:

- queue summaries show approval-aware statuses
- OpenClaw runbook selection exposes blocked reasons instead of raw queue fallbacks