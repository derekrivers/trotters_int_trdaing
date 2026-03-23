# Codebase Notes

First files to inspect:

- `src/trotters_trader/research_families.py`
- `src/trotters_trader/cli.py`
- `configs/directors/`
- `configs/research_programs/`
- `configs/openclaw/trotters-runbook.json`

Key invariants:

- bootstrap is bounded to one proposal id
- generated artifacts stay repo-managed and deterministic
- queue enablement follows approval state, not the bootstrap alone

Regression zones:

- Windows live-stack file locking when writing catalog artifacts
- mismatch between bootstrapped plan ids and runbook entries