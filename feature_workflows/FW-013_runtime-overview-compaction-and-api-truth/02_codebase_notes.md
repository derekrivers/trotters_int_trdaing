# FW-013 Codebase Notes

## Touched Modules

- `src/trotters_trader/api.py`
- `tests/test_api.py`

## Invariants

- overview must keep the same operator-critical fields: health, active state, notifications, current best candidate, entry gate, and research portfolio
- heavy history belongs on dedicated detail endpoints, not the overview route
- live worker and running-job counts must still reflect the shared runtime truth

## Known Smells

- `ApiController.overview()` was mixing summary data with full raw runtime history
- API response growth can hide as a correctness issue if only field presence is tested

## Regression Zones

- `/api/v1/runtime/overview`
- `/readyz`
- any client expecting service-heartbeat data under `status`

## Files To Inspect First

1. `src/trotters_trader/api.py`
2. `tests/test_api.py`
3. `src/trotters_trader/research_runtime.py`
