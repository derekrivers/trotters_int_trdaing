# Lessons

## During Implementation

- the duplicate-campaign bug was not a missing uniqueness check inside `start_campaign()`; it was a launch race in `step_director()` before the queue handoff was durably recorded
- an operator-facing runtime can still be misleading even when counts are compact unless one summary explicitly explains the active branch

## Durable Takeaways

- director launch needs a recoverable claim state whenever queue stepping and campaign creation are split across multiple writes
- runtime truth surfaces should expose explicit warnings for broken invariants instead of assuming "healthy" means internally consistent
