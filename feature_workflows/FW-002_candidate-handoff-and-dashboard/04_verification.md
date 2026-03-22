# Verification

## Repo Checks

- `$env:PYTHONPATH='src'; python -m unittest tests.test_reports tests.test_api tests.test_dashboard -v`

## App Checks

- `docker compose up --build -d`
- `docker compose up -d --scale worker=4`
- `docker compose ps`
- fetch `http://localhost:8888/` and confirm the `Current Best Candidate` section is present
- fetch `http://localhost:8888/guide` and confirm the operator-facing copy is clean
- fetch `http://localhost:8890/api/v1/runtime/overview` with auth and confirm `current_best_candidate` is populated

## OpenClaw Checks

- not required for this workflow because no OpenClaw plugin or skill contract changed

## Expected Signals

- dashboard overview shows a single obvious best-candidate section
- API returns structured operator-ready summary data under `current_best_candidate`
- existing scorecard and comparison pages still render
- live stack remains healthy after rebuild

## Recorded Results

- repo tests passed: `46` tests across `tests.test_reports`, `tests.test_api`, and `tests.test_dashboard`
- live dashboard returned `200` and contained `Current Best Candidate`
- live guide returned `200` and contained the cleaned success text
- live runtime overview returned `healthy` with `1` active director, `1` active campaign, and a populated `current_best_candidate`
- rebuild temporarily collapsed the worker pool to one replica, so the verification path now explicitly restores `--scale worker=4`
