# Verification

## Repo Checks

- search for deleted context doc references:
  - `16_paper_trading_preparation`
  - `17_paper_trade_readiness_review`
  - `18_runtime_agent_api_plan`
  - `19_openclaw_supervisor_next_steps`
  - `22_openclaw_iteration_2_tasklist`
- inspect `feature_workflows/` to confirm the required file set exists

## App Checks

- `docker compose ps`
- fetch the dashboard guide page
- fetch the runtime overview API route with auth

## OpenClaw Checks

- `docker compose exec openclaw-gateway openclaw skills info runtime-supervisor`

## Expected Signals

- no stale references remain in tracked docs
- the running stack stays healthy
- dashboard, API, and OpenClaw still respond normally
