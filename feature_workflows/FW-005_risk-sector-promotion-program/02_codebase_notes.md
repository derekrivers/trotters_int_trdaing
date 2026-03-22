# Codebase Notes

## Touched Areas

- `configs/directors/broad_operability.json`
- the current broad risk/sector config files
- `src/trotters_trader/experiments.py`
- `src/trotters_trader/reports.py`
- `src/trotters_trader/research_runtime.py`
- research catalog and program-report tests

## Invariants

- promotion policy stays strict
- negative results must be preserved as first-class evidence
- artifact generation must stay reproducible and inspectable

## Known Smells

- experiment and reporting logic are concentrated in large modules
- research evidence can be scattered across many runtime outputs unless a single branch context is maintained

## Regression Zones

- comparison and tranche ranking behavior
- operability program reports
- research catalog entries
- director plan execution for the active branch

## Inspect First

1. `context/14_delivery_roadmap.md`
2. `configs/directors/broad_operability.json`
3. `src/trotters_trader/experiments.py`
4. `src/trotters_trader/reports.py`
