# Lessons

## During Implementation

- the missing portfolio route was not a server bug; the real issue was that route discovery and summary contracts were still inconsistent enough to invite wrong assumptions
- active operability work can look like a candidate surface unless the no-candidate state is made explicit and normalized early

## Durable Takeaways

- operator-facing read models need explicit negative states such as `no_selected_candidate`, not just missing fields
- the supervisor queue needs its own truth surface; portfolio summaries alone are not enough to explain whether continuation is actually runnable
