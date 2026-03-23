# Codebase Notes

First files to inspect:

- `src/trotters_trader/research_families.py`
- `src/trotters_trader/api.py`
- `src/trotters_trader/dashboard.py`
- `extensions/openclaw/trotters-runtime/index.js`

Key invariants:

- API, dashboard, and OpenClaw read the same `next_family_status`
- blocked is presented as governed, not ambiguous idle
- active approved family state remains distinct from blocked pending approval

Regression zones:

- wording drift between surfaces
- queue state that looks idle when it is actually active or blocked for governance reasons