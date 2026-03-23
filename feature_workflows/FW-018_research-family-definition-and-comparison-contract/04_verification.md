# Verification

Repo checks run:

- `$env:PYTHONPATH='src'; python -m unittest tests.test_research_families tests.test_api tests.test_dashboard -v`

Live checks run:

- authenticated `GET /api/v1/research-families`
- authenticated `GET /api/v1/research-families/current-proposal`
- authenticated dashboard `GET /`

Expected result:

- API and dashboard show the same approved proposal and family statuses