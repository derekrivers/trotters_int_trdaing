# Codebase Notes

- `src/trotters_trader/dashboard.py`
  - owns `_runtime_health` and the main dashboard rendering
  - currently computes health without awareness of governed next-family blockers
- `src/trotters_trader/api.py`
  - reuses `_runtime_health` for `/api/v1/runtime/overview`
  - should stay aligned with the dashboard because OpenClaw consumes the same overview payload
- `tests/test_dashboard.py`
  - already covers degraded, failed, and idle runtime summaries
- `tests/test_api.py`
  - already covers overview health snapshots and service-heartbeat degradation
