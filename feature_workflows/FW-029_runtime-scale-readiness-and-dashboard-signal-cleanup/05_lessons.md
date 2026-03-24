# Lessons

## During Implementation

- the main SQLite relief came from cutting steady-state write frequency, not from changing the job-completion transaction shape
- moving liveness to `workers.heartbeat_at` simplified stale-worker recovery and removed a second hot-path write target
- the dashboard became materially easier to scan once job churn, agent telemetry, and terminal-outcome tables stopped competing with the live operator story

## Durable Takeaways

- future runtime scale work should keep treating write amplification and export churn as the first bottlenecks to remove before considering a control-plane DB replacement
- overview routes should avoid computing or rendering detail that is no longer shown; payload shaping and presentation cleanup need to land together
- Windows host-to-Docker full-body overview probes can be misleadingly slow even when the service is returning `200`, so health checks plus container access logs are a practical fallback for local verification
