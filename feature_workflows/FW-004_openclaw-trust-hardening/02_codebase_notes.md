# Codebase Notes

## Touched Areas

- `extensions/openclaw/trotters-runtime/index.js`
- `configs/openclaw/openclaw.json`
- `scripts/openclaw/start-openclaw.sh`
- `src/trotters_trader/ops_bridge.py`
- `src/trotters_trader/research_runtime.py`
- `tests/test_openclaw_supervisor_integration.py`
- `tests/test_ops_bridge.py`
- `extensions/openclaw/trotters-runtime/index.test.js`

## Invariants

- `runtime-supervisor` remains the only always-on agent
- mutation stays narrow and allowlisted
- compact tool output remains the default
- repo-managed policy remains authoritative over workspace notes

## Known Smells

- `index.js` still mixes tool definitions, review-pack building, normalization, and decision shaping
- repeated incident behavior is split across runtime notifications, summary writing, and plugin logic

## Regression Zones

- plugin load
- skill discovery
- cron scheduling behavior
- supervisor decision summaries
- ops-bridge restart behavior

## Inspect First

1. `context/20_openclaw_lessons_learned.md`
2. `context/18_openclaw_status_and_backlog.md`
3. `extensions/openclaw/trotters-runtime/index.js`
4. `tests/test_openclaw_supervisor_integration.py`
