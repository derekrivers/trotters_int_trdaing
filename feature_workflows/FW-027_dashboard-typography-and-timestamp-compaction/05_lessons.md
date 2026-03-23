# Lessons

## During Implementation

- the timestamp cleanup was safest when handled by one dashboard-only display helper rather than editing the runtime read models
- typography changes were most effective when applied to the shared layout scale instead of per-section one-offs

## Durable Takeaways

- operator dashboards should default to second precision unless there is a concrete operational reason to show more detail
- once the read model is shared elsewhere, presentation workflows should stay local to `dashboard.py` and its tests
