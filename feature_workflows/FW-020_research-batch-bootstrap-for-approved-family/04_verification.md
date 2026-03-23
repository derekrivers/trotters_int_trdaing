# Verification

Repo checks run:

- `$env:PYTHONPATH='src'; python -m unittest tests.test_research_families tests.test_cli tests.test_catalog tests.test_promotion_path -v`

Live checks run:

- `$env:PYTHONPATH='src'; python -m trotters_trader.cli research-family-bootstrap --proposal-id mean_reversion_broad_reentry --catalog-output-dir runtime/catalog`

Expected result:

- bootstrap returns the program, director, and queue paths
- catalog writes succeed under the running Windows stack