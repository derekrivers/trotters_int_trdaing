# Codebase Notes

## Touched Areas

- `configs/research_programs/risk_sector_promotion.json`
- `configs/directors/risk_sector_promotion.json`
- `src/trotters_trader/cli.py`
- `src/trotters_trader/research_programs.py`
- research-program and CLI tests

## Invariants

- promotion policy stays strict
- negative results must be preserved as first-class evidence
- artifact generation must stay reproducible and inspectable

## Known Smells

- experiment and reporting logic are concentrated in large modules
- research evidence can be scattered across many runtime outputs unless a single branch context is maintained
- runtime history and catalog pointers are not uniformly shaped, so program reports need defensive fallbacks

## Regression Zones

- CLI config loading and output-dir override behavior
- research catalog entries and profile-history lookup
- any future operator surfaces that consume research-program artifacts

## Inspect First

1. `context/14_delivery_roadmap.md`
2. `configs/research_programs/risk_sector_promotion.json`
3. `src/trotters_trader/research_programs.py`
4. `src/trotters_trader/cli.py`
