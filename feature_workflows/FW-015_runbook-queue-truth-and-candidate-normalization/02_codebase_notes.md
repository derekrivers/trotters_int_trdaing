# Codebase Notes

## Touched Areas

- `src/trotters_trader/runbook_queue.py`
- `src/trotters_trader/promotion_path.py`
- `src/trotters_trader/api.py`
- `src/trotters_trader/dashboard.py`
- `tests/test_runbook_queue.py`
- `tests/test_promotion_path.py`
- `tests/test_api.py`
- `tests/test_dashboard.py`

## Invariants

- a queue item can be active, ready, blocked, untracked, or disabled, but the operator should not have to infer that from scattered read models
- `current_best_candidate` must distinguish `available`, `no_selected_candidate`, and `unavailable`
- a no-candidate operability branch must not become a fake candidate record in the progression ledger

## Known Smells

- API and dashboard still rebuild several read models from scratch inside overview handlers
- promotion-path shaping and queue-truth shaping now live in separate modules, so contract drift remains a risk if both change independently

## Regression Zones

- current-best-candidate route and overview payload shape
- research-program portfolio route compatibility
- dashboard overview rendering for candidate and queue summaries

## Inspect First

1. `src/trotters_trader/promotion_path.py`
2. `src/trotters_trader/api.py`
3. `src/trotters_trader/dashboard.py`
4. `src/trotters_trader/runbook_queue.py`
