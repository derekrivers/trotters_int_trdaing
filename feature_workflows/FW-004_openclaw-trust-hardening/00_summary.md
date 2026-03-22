# FW-004 OpenClaw Trust Hardening

## Goal

- raise trust in the OpenClaw operator layer by tightening repeated-incident behavior, drill coverage, plugin trust configuration, and specialist summary quality

## Status

- `ready`

## Dependency Chain

- `FW-001`

## Exit Criteria

- repeated degraded incidents are fingerprinted and cooldown-limited more clearly
- overnight and repeated degraded-cycle drills have stronger coverage
- plugin trust configuration is explicit rather than left as a known warning
- specialist summaries are more decision-ready where the operator depends on them

## Commit Boundaries

- one commit for cooldown/fingerprint behavior and tests
- one commit for plugin trust configuration or summary-quality hardening if they are materially separate
