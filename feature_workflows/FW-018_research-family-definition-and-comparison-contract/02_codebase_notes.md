# Codebase Notes

First files to inspect:

- `src/trotters_trader/research_families.py`
- `src/trotters_trader/api.py`
- `src/trotters_trader/dashboard.py`

Key invariants:

- API and dashboard consume the same comparison builder
- proposal statuses stay in the standard vocabulary
- current proposal resolution is deterministic

Regression zones:

- drift between API payloads and dashboard rendering
- proposal/program status mismatch