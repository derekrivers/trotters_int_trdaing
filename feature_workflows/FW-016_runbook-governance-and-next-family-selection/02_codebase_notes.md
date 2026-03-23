# Codebase Notes

Primary files touched:

- `src/trotters_trader/runbook_queue.py`
- `extensions/openclaw/trotters-runtime/index.js`
- `configs/openclaw/trotters-runbook.json`
- `tests/test_runbook_queue.py`
- `extensions/openclaw/trotters-runtime/index.test.js`
- `tests/test_dashboard.py`

Invariants:

- the queue summary is the shared contract for operator and supervisor reasoning
- OpenClaw should not select a next item that the governed queue summary would reject
- disabled entries may remain in the runbook for history / audit, but they are not runnable
- if no runnable family exists, the correct action is to stop and ask for a new approved family

Regression zones:

- stale continuation fallback to raw queue position one
- BOM-sensitive JSON / JS files after Windows shell rewrites
- dashboard wording drifting away from the governed queue state
