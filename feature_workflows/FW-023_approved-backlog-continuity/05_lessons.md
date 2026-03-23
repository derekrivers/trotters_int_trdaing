# Lessons

- A governed queue needs both safety and continuity. Blocking correctly when the backlog is empty is only half the operator story.
- Queue-head ordering must respect runbook priority; proposal-name sorting is not good enough once multiple approved standby families exist.
- On Windows-hosted repos, config JSON loaders should tolerate UTF-8 BOMs or live file seeding will break in ways that unit tests on BOM-free files do not catch.