# Codebase Notes

## Touched Areas

- `src/trotters_trader/dashboard.py`
- `src/trotters_trader/dashboard_assets.py`
- `src/trotters_trader/assets/dashboard.src.css`
- `src/trotters_trader/assets/dashboard.css`
- `tests/test_dashboard.py`
- `pyproject.toml`

## Invariants

- Python rendering remains the source of truth for dashboard pages and actions
- current dashboard routes, auth, CSRF, and runtime/API contracts must remain behaviorally unchanged

## Known Smells

- dashboard rendering and styling are still concentrated in one Python module
- there is no broader main-app frontend stack, so the asset build must stay narrowly scoped and Python-native

## Regression Zones

- dashboard startup and runtime stack boot if assets become required for the page to render
- operator pages that mix dense data tables, alerts, forms, and status pills
- asset-route auth behavior and cacheability

## Inspect First

1. `src/trotters_trader/dashboard.py`
2. `src/trotters_trader/dashboard_assets.py`
3. `src/trotters_trader/assets/dashboard.src.css`
4. `feature_workflows/FW-027_dashboard-typography-and-timestamp-compaction/`
