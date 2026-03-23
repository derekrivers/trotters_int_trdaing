# FW-009 Codebase Notes

## Touched Modules

- `src/trotters_trader/reports.py`
- `src/trotters_trader/promotion_path.py`
- `src/trotters_trader/api.py`
- `src/trotters_trader/dashboard.py`

## Invariants

- recommendation states must stay conservative and evidence-derived
- read models must tolerate partial historical artifacts without crashing
- runtime/catalog persistence should be additive and readable from outside the dashboard

## Known Smells

- candidate shaping had started to drift across `reports.py`, `api.py`, and `dashboard.py`
- the dashboard previously risked becoming the only place where some operator-facing synthesis existed

## Regression Zones

- current-best-candidate rendering
- API overview payload shape
- paper-rehearsal code that depends on candidate identity

## Files To Inspect First

1. `src/trotters_trader/reports.py`
2. `src/trotters_trader/api.py`
3. `src/trotters_trader/dashboard.py`
4. `tests/test_api.py`
5. `tests/test_dashboard.py`
