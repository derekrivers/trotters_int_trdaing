# Verification

## Repo Checks

- targeted tests for any runbook, director, research-program, or supervisor-decision changes
- confirm no stale references still point to the retired `risk + sector` family as the active branch

## App Checks

- `docker compose ps`
- verify dashboard/system health remains healthy after runbook changes
- verify the runtime still shows no duplicate active directors or campaigns after the next family is started

## OpenClaw Checks

- `openclaw skills info runtime-supervisor`
- verify the supervisor sees the updated runbook and can resolve the new next work item
- verify the stale-context guard still prevents accidental churn

## Expected Signals

- a next approved research item exists
- the supervisor no longer stalls simply because the queue ended
- the new branch still respects explicit stop conditions instead of running indefinitely
