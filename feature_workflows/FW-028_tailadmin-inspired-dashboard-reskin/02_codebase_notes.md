# Codebase Notes

## Touched Areas

- `src/trotters_trader/dashboard.py`
- dashboard asset serving and layout wiring
- Docker/startup/docs if a minimal asset build must become part of the local runtime path

## Invariants

- Python rendering remains the source of truth for dashboard pages and actions
- current dashboard routes, auth, CSRF, and runtime/API contracts must remain behaviorally unchanged

## Known Smells

- dashboard rendering and styling are still concentrated in one Python module
- there is no main-app frontend asset pipeline yet, so introducing one needs strict scope control

## Regression Zones

- dashboard startup and runtime stack boot if assets become required for the page to render
- operator pages that mix dense data tables, alerts, forms, and status pills

## Inspect First

1. `src/trotters_trader/dashboard.py`
2. `feature_workflows/FW-027_dashboard-typography-and-timestamp-compaction/`
