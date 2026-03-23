# Lessons

- A queue-alignment warning is not enough if the actual continuation tool still trusts raw queue order.
- On Windows, direct PowerShell rewrites can silently add a UTF-8 BOM and break JSON or plugin loading contracts. Rewriting with UTF-8 without BOM is mandatory for OpenClaw-facing files.
- The correct terminal state for the supervisor queue is sometimes "empty and blocked pending approval", not "find something else to run".
