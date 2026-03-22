# Lessons

## During Implementation

- do not let the dashboard invent recommendation logic that already belongs in persisted artifacts
- the safest source of truth for operator handoff is the existing operability scorecard, not whichever artifact happened to be easiest to read in the view layer
- overview features need summary fallbacks when a detailed campaign lookup is unavailable, otherwise a missing detail row can turn the whole page into a `400`

## Durable Takeaways

- operator clarity is a data-contract problem first and a page-layout problem second
- if a rebuild is part of verification, restore the intended worker scale explicitly because `docker compose up --build -d` drops replica counts back to the compose default
- when a feature changes what the operator sees first, verify the real running page and API rather than trusting fixture-only tests
