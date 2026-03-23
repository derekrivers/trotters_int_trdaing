# Codebase Notes

First files to inspect:

- `configs/research_family_proposals/`
- `src/trotters_trader/research_families.py`
- `configs/research_programs/`
- `configs/directors/`

Key invariants:

- a proposal is incomplete if it lacks `why_different_from_retired` or `stop_conditions`
- approval state must be explicit and machine-readable
- one proposal may be approved, but it is not runnable until the queue/governance path accepts it

Regression zones:

- weak proposal validation
- status vocabulary drift between proposal and program layers