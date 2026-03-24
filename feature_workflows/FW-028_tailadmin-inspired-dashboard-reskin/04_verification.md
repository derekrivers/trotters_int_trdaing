# Verification

## Repo Checks

- `python -m trotters_trader.dashboard_assets`
- `$env:PYTHONPATH='src'; python -m unittest tests.test_dashboard`

## App Checks

- start `python -m trotters_trader.cli research-dashboard --runtime-root runtime/live_dashboard_smoke --dashboard-host 127.0.0.1 --dashboard-port 8899 --dashboard-refresh-seconds 0`
- verify `http://127.0.0.1:8899/healthz`
- verify authenticated `GET /`
- verify authenticated `GET /assets/dashboard.css`

## OpenClaw Checks

- none expected beyond confirming the dashboard still reflects the same runtime truth

## Expected Signals

- the dashboard renders with TailAdmin-inspired styling without breaking existing operator routes
- asset build and runtime startup are reproducible from a fresh checkout
- the overview HTML links the compiled stylesheet instead of embedding inline CSS
