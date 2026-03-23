# Verification

- `$env:PYTHONPATH=''src''; python -m unittest tests.test_active_branch tests.test_research_programs tests.test_research_families tests.test_runbook_queue tests.test_dashboard tests.test_api` passed: `73` tests.
- Restarted `research-api` and `dashboard` on the updated code.
- Verified in the live `research-api` container that the governed queue exposes:
  - `next_runnable_plan_id = sma_cross_broad_confirmation`
  - `standby_ready_depth = 3`
  - `continuity_status = healthy`
  - `approved_backlog_plan_ids = [mean_reversion_broad_fastcycle, momentum_drawdown_sector_guard]` once the head is active.
- Started the new queue head in the live runtime and verified:
  - active director `sma-cross-confirmation-director`
  - active campaign `sma-cross-confirmation-primary`
  - queued/running jobs present
  - approved standby backlog depth remains `2` behind the active family.
- Verified the dashboard continues serving `GET /` with `200` after the backlog changes, and the health endpoint continues returning `200` in container logs.