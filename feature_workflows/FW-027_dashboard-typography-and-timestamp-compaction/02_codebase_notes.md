# Codebase Notes

## Touched Areas

- `src/trotters_trader/dashboard.py`
- dashboard CSS and timestamp-formatting helpers

## Invariants

- dashboard routes, auth, CSRF, and operator actions must behave exactly as they do now
- runtime/API read-model truth should remain unchanged; this workflow is presentation-first

## Known Smells

- one large dashboard module still owns routing, rendering, styling, and formatting
- timestamp strings are sometimes too raw for an operator-facing UI

## Regression Zones

- health/system status banners and detail pages that combine raw timestamps with relative-age labels
- tests that assert exact timestamp text or specific heading/card content

## Inspect First

1. `src/trotters_trader/dashboard.py`
2. `tests/test_dashboard.py`
