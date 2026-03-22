# Lessons

## During Implementation

- stronger infrastructure throughput does not count as stronger strategy evidence
- if a branch is "current best" but still policy-negative, it needs a hard terminal follow-up and a retirement rule, not indefinite operator optimism
- research program artifacts need to tolerate partial catalog metadata because older runtime paths do not always populate the catalog in a uniform way

## Durable Takeaways

- research branches need explicit retirement criteria or they silently turn into endless tuning programs
- branch definitions should be repo-managed config, not only inferred from roadmap prose or old runtime directories
- when a branch is rerun live, write its artifacts into the same catalog used by the app so the evidence trail does not split across `runs/` and `runtime/catalog/`
