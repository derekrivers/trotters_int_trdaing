# Codebase Notes

## Touched Areas

- `configs/openclaw/trotters-runbook.json`
- `configs/directors/*.json`
- `configs/research_programs/*.json`
- `src/trotters_trader/experiments.py`
- `src/trotters_trader/research_runtime.py`
- `src/trotters_trader/research_programs.py`
- OpenClaw supervisor/runbook tests if queue semantics change

## Invariants

- every automatically started branch must be explicitly approved in repo config
- a retired branch must stay retired unless new evidence and a new workflow explicitly reopen it
- the supervisor should only auto-advance into fresh, intentional work

## Known Smells

- the repo still mixes strategy-family selection logic across roadmap prose, director configs, and experiment code
- runbook continuity currently depends on a single JSON queue with no higher-level `research program registry`
- experiment generation remains concentrated in `experiments.py`, making next-family selection harder to reason about

## Regression Zones

- runbook queue ordering and fallback behavior
- director/campaign duplicate prevention
- supervisor stale-context safeguards
- any dashboard/API view that assumes `broad_operability` is still the current path

## Inspect First

1. `runtime/catalog/risk_sector_promotion_program/research_program.json`
2. `configs/openclaw/trotters-runbook.json`
3. `configs/directors/broad_operability.json`
4. `src/trotters_trader/experiments.py`
5. `extensions/openclaw/trotters-runtime/index.js`
