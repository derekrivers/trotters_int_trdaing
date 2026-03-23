# Codebase Notes

## Touched Areas

- `src/trotters_trader/research_runtime.py`
- `src/trotters_trader/active_branch.py`
- `src/trotters_trader/api.py`
- `src/trotters_trader/dashboard.py`
- `tests/test_active_branch.py`
- `tests/test_research_runtime.py`
- `tests/test_api.py`
- `tests/test_dashboard.py`

## Invariants

- a single running director should have at most one active campaign for the current queue entry
- the queue entry state must remain recoverable if the process dies after claiming launch but before writing `current_campaign_id`
- the dashboard and API should render the same operator-facing branch truth instead of diverging view logic

## Known Smells

- `research_runtime.py` still owns both orchestration and recovery logic, so launch-claim behavior adds more state handling to a large module
- `dashboard.py` continues to mix routing, HTML, and operator view-model shaping even though the branch summary is now shared

## Regression Zones

- director stepping and campaign launch recovery
- API overview payload shape
- dashboard overview rendering when there is no active director or no current campaign

## Inspect First

1. `src/trotters_trader/research_runtime.py`
2. `src/trotters_trader/api.py`
3. `src/trotters_trader/dashboard.py`
4. `tests/test_research_runtime.py`
