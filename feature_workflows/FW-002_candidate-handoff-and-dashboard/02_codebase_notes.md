# Codebase Notes

## Touched Areas

- `src/trotters_trader/dashboard.py`
- `src/trotters_trader/api.py`
- `src/trotters_trader/reports.py`
- `tests/test_dashboard.py`
- `tests/test_api.py`
- `tests/test_reports.py`

## Invariants

- persisted scorecards and report artifacts stay the source of truth
- operator-facing summaries should prefer compact, decision-ready language
- the API should expose structured summaries rather than force dashboard-only interpretation

## Known Smells

- `dashboard.py` mixes routing, HTML generation, formatting, and view-model shaping
- candidate selection logic risks being duplicated between reports, dashboard, and API

## Regression Zones

- overview page summary cards
- campaign handoff pages
- candidate scorecard and comparison rendering
- API routes that already return runtime overview and agent summaries

## Inspect First

1. `src/trotters_trader/dashboard.py`
2. `src/trotters_trader/api.py`
3. `src/trotters_trader/reports.py`
4. `tests/test_dashboard.py`
