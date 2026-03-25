# FW-030 Architecture Overhaul

## Goal

- choose the next runtime control-plane database after SQLite, implement the repo seam for that backend, and record the staged architecture-overhaul plan that follows from that choice
- introduce Postgres-ready runtime support without breaking the live SQLite-backed stack before a dedicated state-migration workflow exists

## Status

- `done`

## Dependency Chain

- `FW-008`
- `FW-026`
- `FW-029`

## Exit Criteria

- runtime orchestration can target Postgres through one shared runtime DB adapter while keeping SQLite available for the current live stack, isolated tests, and host-only fallback runs
- Docker Compose provisions a first-class Postgres service behind an explicit `postgres` profile, and the startup script can opt into that backend deliberately instead of switching the live stack implicitly
- workflow planning and stable architecture docs record the Postgres choice plus the next staged optimization moves beyond this DB seam
- repo verification covers the DB adapter path, SQLite fallback regression checks, full containerized regression coverage, and disposable live verification on the Postgres-backed stack

## Commit Boundaries

- workflow scaffolding, board updates, hotspot ownership, and stable architecture-doc updates
- runtime DB adapter, runtime-path/config changes, Compose/runtime-start wiring, and verification coverage
- disposable live verification, workflow closeout, and clean commit