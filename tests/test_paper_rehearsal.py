from __future__ import annotations

from datetime import date
from pathlib import Path
import json

from trotters_trader.paper_rehearsal import (
    load_paper_actions,
    load_paper_days,
    load_paper_state,
    paper_rehearsal_status,
    record_paper_trade_action,
    run_paper_trade_runner,
)
from tests.support import IsolatedWorkspaceTestCase


class PaperRehearsalTests(IsolatedWorkspaceTestCase):
    def test_runner_blocks_when_no_promoted_candidate_exists(self) -> None:
        catalog_output_dir = self.temp_root / "catalog"

        payload = run_paper_trade_runner(catalog_output_dir, reference_date=date(2026, 3, 22))

        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["day"]["block_reasons"][0]["code"], "no_promoted_candidate")
        self.assertEqual(load_paper_days(catalog_output_dir, limit=1)[0]["status"], "blocked")
        self.assertEqual(load_paper_actions(catalog_output_dir, limit=1)[0]["action"], "blocked")
        self.assertEqual(paper_rehearsal_status(catalog_output_dir)["entry_gate"]["status"], "blocked")

    def test_runner_and_accept_action_persist_stateful_rehearsal_records(self) -> None:
        catalog_output_dir = self.temp_root / "catalog"
        config_path = self.temp_root / "promoted.toml"
        config_path.write_text(
            Path("configs/backtest.toml")
            .read_text(encoding="utf-8")
            .replace('output_dir = "runs"', f'output_dir = "{(self.temp_root / "runs").as_posix()}"')
            .replace('frozen_on = ""', 'frozen_on = "2026-03-21"')
            .replace("promoted = false", "promoted = true"),
            encoding="utf-8",
        )

        runner_payload = run_paper_trade_runner(catalog_output_dir, config_path=str(config_path))
        action_payload = record_paper_trade_action(
            catalog_output_dir,
            action="accepted",
            day_id=runner_payload["day"]["day_id"],
            actor="test-operator",
            reason="paper rehearsal accepted",
        )
        status = paper_rehearsal_status(catalog_output_dir, limit=5)

        self.assertEqual(runner_payload["status"], "ready")
        self.assertEqual(action_payload["status"], "recorded")
        self.assertTrue(load_paper_state(catalog_output_dir)["portfolio"]["initialized"])
        self.assertEqual(status["latest_action"]["action"], "accepted")
        self.assertEqual(status["latest_day"]["status"], "ready")
        self.assertEqual(status["entry_gate"]["status"], "ready")
