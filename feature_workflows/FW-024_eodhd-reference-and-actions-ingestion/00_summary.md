# FW-024 EODHD Reference And Actions Ingestion

Status: `done`

## Goal

Move the EODHD path beyond daily bars alone by ingesting exchange-symbol metadata plus split and dividend feeds, then feed those generated artifacts back into the existing staging and canonical pipeline.

## Dependency Chain

- `FW-023` kept the governed research queue running with enough approved standby depth.
- `FW-024` improves the quality of the data feeding those research families by replacing static/sample EODHD support files with generated vendor-backed reference and corporate-action artifacts.

## Exit Criteria

- the repo can download EODHD exchange-symbol metadata into an instrument master
- the repo can download EODHD dividends and splits into a normalized corporate-action CSV
- a managed EODHD config can materialize canonical data using `splits_and_dividends_from_actions`
- regression tests cover the new download paths and total-return materialization
- live verification confirms the configured EODHD key can access the new endpoints and produce a canonical dataset

## Commit Boundaries

1. EODHD client/config/CLI support for reference and corporate-action downloads
2. managed total-return config plus ingestion regression coverage
3. README and workflow-board updates
