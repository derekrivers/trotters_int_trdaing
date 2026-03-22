# Feature Workflows

This directory is the active planning and execution layer for the repo.

Use it for:

- per-feature or per-job context
- implementation plans
- verification checklists
- codebase smell notes tied to a concrete workflow
- post-work lessons before they are merged into stable documentation

Do not use `context/` for temporary feature execution notes.
`context/` remains the stable reference layer for architecture, domain, governance, and current high-level status.

## Status Model

- `proposed`
- `ready`
- `in_progress`
- `verifying`
- `done`
- `archived`

## Folder Shape

Each feature workflow folder should contain exactly:

- `00_summary.md`
- `01_context.md`
- `02_codebase_notes.md`
- `03_plan.md`
- `04_verification.md`
- `05_lessons.md`

Use the files under `templates/` when creating a new workflow.

## Workflow Rules

1. One workflow should answer one operator, runtime, research, or platform problem.
2. Code-smell cleanup must be tied to the workflow that benefits from it.
3. Verification must include both repo-level checks and app-status checks.
4. Durable lessons should be merged back into `context/` or another stable doc before a workflow is archived.
5. If a workflow is still driving implementation, keep it here rather than recreating its notes elsewhere.

## Archive Rule

Completed workflows stay in place until their durable lessons have been merged into stable documentation.
After that, move them into `archive/`.

## Current Entry Points

- `00_program_board.md` for the active queue
- `01_code_hotspots.md` for the repo-wide smell register
- `FW-001_docs-and-planning-sync/` for the workflow that established this structure
