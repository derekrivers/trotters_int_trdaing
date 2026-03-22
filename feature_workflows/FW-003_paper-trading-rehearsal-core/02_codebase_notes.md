# Codebase Notes

## Touched Areas

- `src/trotters_trader/reports.py`
- `src/trotters_trader/cli.py`
- `src/trotters_trader/research_runtime.py` only if needed for shared persistence or exports
- any new paper-state module created for this workflow
- tests around paper-trade decision generation and operator surfaces

## Invariants

- paper state must be separate from research runtime state
- research artifacts remain immutable evidence
- blocked days must be explicit, auditable outcomes
- operator actions must be persisted, not inferred from missing files

## Known Smells

- paper-trade decision logic currently lives too close to report generation
- `research_runtime.py` already carries too many concerns and should only be touched if the workflow truly needs shared runtime/export behavior

## Regression Zones

- existing `paper-trade-decision` behavior
- report artifact generation
- dashboard/API surfaces that summarize candidate readiness

## Inspect First

1. `context/16_paper_trading_status.md`
2. `src/trotters_trader/reports.py`
3. `src/trotters_trader/cli.py`
4. paper-trade related tests
