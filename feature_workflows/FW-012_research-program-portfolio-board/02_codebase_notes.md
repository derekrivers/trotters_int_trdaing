# FW-012 Codebase Notes

## Touched Modules

- `src/trotters_trader/promotion_path.py`
- `src/trotters_trader/research_programs.py`
- `src/trotters_trader/api.py`
- `src/trotters_trader/dashboard.py`

## Invariants

- repo-managed research-program definitions remain the source of truth
- retired programs must not appear as implied leading branches
- queue eligibility should reflect the runbook, not ad hoc directory scanning

## Known Smells

- branch-selection knowledge had drifted between workflow docs, runbook config, and runtime artifacts
- the operator had no single compact view for program portfolio state

## Regression Zones

- research-program summary generation
- runtime overview payload size and stability
- dashboard readability when many programs accumulate

## Files To Inspect First

1. `src/trotters_trader/research_programs.py`
2. `src/trotters_trader/promotion_path.py`
3. `configs/openclaw/trotters-runbook.json`
