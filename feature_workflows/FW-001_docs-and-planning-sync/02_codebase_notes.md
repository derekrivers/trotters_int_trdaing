# Codebase Notes

## Touched Areas

- `README.md`
- `context/README.md`
- `context/14_delivery_roadmap.md`
- `context/15_phase10_tasklist.md`
- `feature_workflows/*`

## Invariants

- `context/` must remain the stable reference layer
- active feature execution notes must live under `feature_workflows/`
- this workflow must not change runtime, research, or OpenClaw behavior

## Known Smells

- top-level docs can drift after file renames or context consolidation
- duplicate planning surfaces age badly if one is not clearly authoritative

## Regression Zones

- stale markdown links to deleted docs
- misleading Phase 10 sequencing that no longer matches the implemented repo state

## Inspect First

1. `context/README.md`
2. `context/14_delivery_roadmap.md`
3. `context/15_phase10_tasklist.md`
4. `README.md`
