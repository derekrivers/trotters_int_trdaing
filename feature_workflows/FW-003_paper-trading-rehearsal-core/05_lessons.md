# Lessons

## During Implementation

- keep paper rehearsal separate from research orchestration or the boundary will blur quickly
- a blocked paper day should be written as a first-class record, not left as a missing output or an implied warning
- the runner needs its own state and action log even when the current live outcome is only `blocked`

## Durable Takeaways

- paper trading needs state and operator decisions, not just daily exports
- the safest source of truth for promoted-candidate resolution is the persisted promotion history, not whichever summary happens to be on the dashboard
- rebuild-based verification needs an explicit worker rescale step because Compose resets replicas to the service default
