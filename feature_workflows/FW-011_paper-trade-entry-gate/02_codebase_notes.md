# FW-011 Codebase Notes

## Touched Modules

- `src/trotters_trader/paper_rehearsal.py`
- `src/trotters_trader/promotion_path.py`
- `src/trotters_trader/api.py`
- `src/trotters_trader/dashboard.py`

## Invariants

- the paper runner must remain conservative
- explicit block reasons should survive even when evidence is partial
- gate evaluation should be inspectable without running a paper day

## Known Smells

- rehearsal runner logic and readiness evaluation were previously intertwined
- gate semantics risked being inferred differently in API and dashboard if not centralized

## Regression Zones

- paper-trade status endpoint
- daily paper-runner behavior
- dashboard paper-rehearsal panel

## Files To Inspect First

1. `src/trotters_trader/paper_rehearsal.py`
2. `src/trotters_trader/promotion_path.py`
3. `tests/test_paper_rehearsal.py`
