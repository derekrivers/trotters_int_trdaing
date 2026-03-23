# FW-026 Summary

## Goal

Reduce architecture drift between the dashboard and API by moving shared runtime-overview assembly into one module that owns compact/full status shaping, health, notifications, terminal summaries, and governed queue read models.

## Delivered

- added `src/trotters_trader/runtime_overview.py` as the shared read-model layer for overview payload assembly
- moved runtime health, notification loading, terminal-summary selection, and compact overview shaping out of dashboard/API-local helpers
- updated `DashboardController.overview()` and `ApiController.overview()` to delegate to the shared builder while keeping route-specific presentation and transport behavior local
- updated dashboard tests to freeze the shared runtime-overview clock where health timing is asserted

## Verification

- `PYTHONPATH=src python -m unittest tests.test_api tests.test_dashboard`
- `57` tests passed

## Follow-On Rule

Future operator-overview changes should land in `runtime_overview.py` first. The dashboard and API should stay focused on rendering, auth, transport, and endpoint-specific concerns rather than rebuilding shared runtime summaries independently.
