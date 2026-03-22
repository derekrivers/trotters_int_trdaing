---
name: failure-investigator
description: "Investigate director or campaign failures using notifications, campaign detail, job detail, and job stderr/stdout tails before choosing a recovery action."
user-invocable: false
---

# Failure Investigator

When a director or campaign failed or stopped:

1. Read `trotters_overview`.
2. Read the latest notifications and terminal summary.
3. Inspect the relevant director or campaign detail.
4. Find the failed jobs and inspect stderr before taking action.

Classify the incident into one of:

- transient runtime fault
- repeat failure of same class
- exhausted search branch
- service-health fault
- ambiguous or missing evidence

Only after classification should you choose retry, fallback, service restart, or escalation.
