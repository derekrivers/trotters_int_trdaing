# Lessons

## During Implementation

- the real migration boundary was not "rewrite all runtime SQL", it was "introduce one compatibility seam for connection semantics and placeholder translation, then keep the rest of the runtime contract stable"
- moving the DB choice into shared runtime configuration is necessary before any later service-boundary, observability, or remote-operations work can stay coherent
- forcing Postgres as an implicit Compose default before a live-state migration path exists is the wrong rollout shape; stage the backend behind explicit config first, then design migration and rollback deliberately

## Durable Takeaways

- Postgres is the correct next-step control-plane store for this Compose runtime because worker, campaign, and director concurrency now matters more than pure single-host simplicity
- SQLite should remain the safe live default until the repo has an explicit runtime-state migration workflow and cutover plan
- the next architecture-overhaul stages should be sequenced after this DB seam: first extract more runtime responsibilities out of `research_runtime.py`, then harden API/server and observability, then revisit filesystem-heavy artifact flows only when the control-plane store is no longer the main bottleneck
- seemingly unrelated integration coverage still matters during platform work; the OpenClaw bootstrap path broke under the new test cycle and needed a small installer-fallback hardening fix to keep the suite clean