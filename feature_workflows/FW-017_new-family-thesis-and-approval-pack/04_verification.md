# Verification

Repo checks run:

- `$env:PYTHONPATH='src'; python -m unittest tests.test_research_families -v`

Expected result:

- proposal validation rejects missing rationale/stop-condition fields
- the approved proposal loads as the current proposal