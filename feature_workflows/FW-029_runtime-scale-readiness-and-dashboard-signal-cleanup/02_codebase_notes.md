# Codebase Notes

## Touched Areas

- `src/trotters_trader/research_runtime.py`
- `src/trotters_trader/runtime_overview.py`
- `src/trotters_trader/dashboard.py`
- `tests/test_research_runtime.py`
- `tests/test_dashboard.py`

## Invariants

- SQLite remains the runtime control-plane store
- dashboard and API auth, CSRF, and route structure remain unchanged
- operator-facing overview keeps the core runtime, candidate, and queue story visible

## Known Smells

- runtime liveness, leasing, exports, and orchestration remain concentrated in one hotspot module
- the dashboard overview is currently carrying both operator-critical signal and lower-value diagnostic repetition

## Regression Zones

- worker leasing and stale-worker recovery
- coordinator export behavior
- API/dashboard freshness under higher worker counts
- overview tests that assert section presence or absence

## Inspect First

1. `src/trotters_trader/research_runtime.py`
2. `src/trotters_trader/runtime_overview.py`
3. `src/trotters_trader/dashboard.py`
4. `tests/test_research_runtime.py`
5. `tests/test_dashboard.py`
