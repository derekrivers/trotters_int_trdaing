# FW-018 Research-Family Definition And Comparison Contract

Status: `done`

## Goal

Expose a single comparison contract for proposals and approved programs so the operator, API, dashboard, and supervisor all read the same family-status model.

## Dependency Chain

- `FW-017` created the proposal artifact.
- `FW-018` turns proposal and program state into shared read models.

## Exit Criteria

- API exposes family-comparison and current-proposal routes
- dashboard renders the same comparison summary
- status vocabulary is standardized across proposals and programs

## Commit Boundaries

1. read-model code and API/dashboard integration
2. workflow and roadmap documentation