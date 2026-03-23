# Verification

## Repo Checks

- dashboard asset build command
- dashboard-focused tests

## App Checks

- restart `dashboard`
- verify `http://127.0.0.1:8888/healthz`
- verify authenticated `GET /`

## OpenClaw Checks

- none expected beyond confirming the dashboard still reflects the same runtime truth

## Expected Signals

- the dashboard renders with TailAdmin-inspired styling without breaking existing operator routes
- asset build and runtime startup are reproducible from a fresh checkout
