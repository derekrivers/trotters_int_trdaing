---
name: service-recovery
description: "Use ops-bridge for narrow service restarts only after confirming a service-health symptom and checking the current restart limits."
user-invocable: false
---

# Service Recovery

Service restarts are the last narrow remediation step before escalation.

Only use `trotters_service.restart` when:

- the runtime API or worker/director service is clearly unhealthy
- the incident cannot be resolved at the director/campaign level
- the restart limit has not already been reached

Never restart more than one service in the same incident unless the evidence clearly justifies a second step.
