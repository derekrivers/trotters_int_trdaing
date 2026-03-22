# Verification

## Repo Checks

- `python -m unittest tests.test_dashboard tests.test_api tests.test_reports -v`

## App Checks

- `docker compose ps`
- fetch `http://localhost:8888/`
- fetch `http://localhost:8890/api/v1/runtime/overview` with auth and confirm the new candidate summary fields

## OpenClaw Checks

- if any summary contract used by OpenClaw changes, re-check `/api/v1/agent-summaries` and the dashboard overview

## Expected Signals

- dashboard overview shows a single obvious best-candidate section
- API returns structured operator-ready summary data
- existing scorecard and comparison pages still render
