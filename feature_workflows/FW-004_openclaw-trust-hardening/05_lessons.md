# Lessons

## During Implementation

- OpenClaw trust issues usually come from drift between repo intent, runtime state, and gateway configuration
- `plugins.allow` was not enough on its own for a repo-copied runtime config; the custom plugin also needed `plugins.load.paths`
- even with the right trust config, bootstrap order matters: the gateway cannot validate trust for a custom plugin before the plugin path exists

## Durable Takeaways

- trust hardening needs code tests and gateway verification together or the result is misleading
- explicit plugin trust should be applied in two stages: bootstrap-safe config first, final trusted config after plugin install
- supervisor trust should be enforced in machine-readable decision fields, not only in prompt wording
