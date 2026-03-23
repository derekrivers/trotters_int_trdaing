# Codebase Notes

- `src/trotters_trader/research_families.py` now owns queue-head ordering for approved families, approved standby backlog depth, and the backlog fields reused by API and dashboard.
- `src/trotters_trader/runbook_queue.py` already knew how to find the next runnable item; this workflow adds explicit continuity depth and backlog messaging without treating low backlog as a hard queue fault.
- `src/trotters_trader/dashboard.py` remains the main operator surface, so the backlog metrics needed to appear there alongside the governed next-family state.
- New family artifacts live under `configs/research_family_proposals/`, `configs/directors/`, `configs/research_programs/`, and fresh repo-supported seed configs under `configs/*.toml`.
- Windows-authored JSON files can pick up a UTF-8 BOM, so the config loaders that read runbook, proposal, program, and plan files were hardened to accept `utf-8-sig`.