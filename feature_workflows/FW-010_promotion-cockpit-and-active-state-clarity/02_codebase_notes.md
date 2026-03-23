# FW-010 Codebase Notes

## Touched Modules

- `src/trotters_trader/dashboard.py`
- `src/trotters_trader/api.py`
- `tests/test_dashboard.py`
- `tests/test_api.py`

## Invariants

- dashboard and API must agree on summary semantics
- live runtime state must not be inferred from terminal history panels
- authenticated dashboard posture from `FW-008` must remain intact

## Known Smells

- `dashboard.py` still mixes routing, HTML construction, and view-model shaping
- panel naming and ordering can create false operator impressions even when the underlying data is correct

## Regression Zones

- overview page render
- guide page references to runtime state
- active campaign / active director counts

## Files To Inspect First

1. `src/trotters_trader/dashboard.py`
2. `src/trotters_trader/api.py`
3. `tests/test_dashboard.py`
