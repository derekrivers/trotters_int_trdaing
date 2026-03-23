# Codebase Notes

First files to inspect:

- `src/trotters_trader/runbook_queue.py`
- `src/trotters_trader/api.py`
- `extensions/openclaw/trotters-runtime/index.js`
- `configs/openclaw/trotters-runbook.json`

Key invariants:

- no runbook item is runnable unless its family is approved
- missing-definition and rejected families stay blocked
- OpenClaw consumes governed summaries, not raw queue order

Regression zones:

- queue status wording
- supervisor follow-up selection