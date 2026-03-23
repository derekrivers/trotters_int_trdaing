from __future__ import annotations

import json
from pathlib import Path

from trotters_trader.promotion_path import (
    build_candidate_progression_summary,
    build_paper_trade_entry_gate,
    build_research_program_portfolio,
    resolve_current_best_candidate,
)
from tests.support import IsolatedWorkspaceTestCase


class PromotionPathTests(IsolatedWorkspaceTestCase):
    def test_research_program_portfolio_marks_queue_entries(self) -> None:
        catalog_output_dir = self.temp_root / "catalog"

        summary = build_research_program_portfolio(catalog_output_dir)

        self.assertEqual(summary["summary_type"], "research_program_portfolio")
        self.assertGreaterEqual(summary["counts"]["total"], 3)
        beta_program = next(
            program
            for program in summary["programs"]
            if program["program_id"] == "beta_defensive_continuation_program"
        )
        self.assertTrue(beta_program["queue_enabled"])
        self.assertEqual(beta_program["queue_plan_id"], "beta_defensive_continuation")

    def test_candidate_progression_summary_merges_current_best_candidate(self) -> None:
        catalog_output_dir = self.temp_root / "catalog"
        history_dir = catalog_output_dir / "profile_history"
        history_dir.mkdir(parents=True, exist_ok=True)
        (history_dir / "candidate-profile.jsonl").write_text(
            json.dumps(
                {
                    "recorded_at_utc": "2026-03-23T10:00:00+00:00",
                    "config_path": "configs/eodhd_momentum_broad_candidate_refine_n4_ms002_rf63.toml",
                    "eligible": False,
                    "recommended_action": "retain",
                    "current_promoted": False,
                    "profile": {
                        "profile_name": "candidate-profile",
                        "profile_version": "2026-03-23.1",
                        "frozen_on": "2026-03-23",
                    },
                    "split_summary": {
                        "validation": {"status": "warn", "excess_return": -0.01},
                        "holdout": {"status": "fail", "excess_return": -0.02},
                    },
                    "walkforward_summary": {"eligible": False, "pass_windows": 1},
                    "fail_reasons": ["holdout_not_pass"],
                }
            )
            + "\n",
            encoding="utf-8",
        )

        summary = build_candidate_progression_summary(
            catalog_output_dir,
            current_best_candidate={
                "campaign_id": "campaign-1",
                "campaign_name": "refine-seed-primary",
                "campaign_status": "running",
                "campaign_updated_at": "2026-03-23T11:00:00+00:00",
                "operator_recommendation": "needs_more_research",
                "headline": "Still needs stronger holdout evidence.",
                "best_candidate": {
                    "run_name": "candidate-run",
                    "profile_name": "candidate-profile",
                    "validation_excess_return": 0.03,
                    "holdout_excess_return": -0.01,
                    "walkforward_pass_windows": 2,
                },
                "what_failed_or_is_missing": ["Holdout excess return is not yet convincingly positive."],
                "next_action": "continue_research",
                "progression": {"selected_candidate_eligible": False},
                "artifact_paths": {"scorecard_json": "runtime/catalog/campaign-1/operator_scorecard.json"},
                "supporting_summaries": {},
                "source": "active_campaign",
            },
        )

        self.assertEqual(summary["summary_type"], "candidate_progression_summary")
        candidate_record = next(
            record
            for record in summary["records"]
            if record["profile_name"] == "candidate-profile"
        )
        self.assertEqual(candidate_record["source_type"], "active_campaign")
        self.assertEqual(candidate_record["run_name"], "candidate-run")
        self.assertEqual(candidate_record["validation_excess_return"], 0.03)

    def test_candidate_progression_ignores_current_best_candidate_without_selected_candidate(self) -> None:
        catalog_output_dir = self.temp_root / "catalog"

        summary = build_candidate_progression_summary(
            catalog_output_dir,
            current_best_candidate={
                "status": "no_selected_candidate",
                "campaign_id": "campaign-1",
                "campaign_name": "broad-operability-primary",
                "campaign_status": "running",
                "campaign_updated_at": "2026-03-23T11:00:00+00:00",
                "operator_recommendation": "needs_more_research",
                "headline": "No candidate is ready.",
                "best_candidate": None,
                "what_failed_or_is_missing": ["No selected candidate is available for operator review."],
                "next_action": "continue_research",
                "progression": {"selected_candidate_eligible": False},
                "artifact_paths": {},
                "supporting_summaries": {},
                "source": "active_campaign",
            },
        )

        self.assertTrue(all(record["campaign_id"] != "campaign-1" for record in summary["records"]))

    def test_resolve_current_best_candidate_normalizes_missing_selected_candidate(self) -> None:
        catalog_output_dir = self.temp_root / "catalog"

        summary = resolve_current_best_candidate(
            catalog_output_dir=catalog_output_dir,
            active_campaigns=[
                {
                    "campaign_id": "campaign-1",
                    "campaign_name": "broad-operability-primary",
                    "status": "running",
                    "phase": "stability_pivot",
                    "updated_at": "2026-03-23T11:00:00+00:00",
                    "state": {
                        "control_row": {
                            "run_name": "control-run",
                            "profile_name": "control-profile",
                            "validation_excess_return": -0.02,
                            "holdout_excess_return": -0.03,
                            "walkforward_pass_windows": 1,
                        },
                        "shortlisted": [],
                        "stress_results": [],
                        "final_decision": {
                            "recommended_action": "continue_research",
                            "reason": "campaign_in_progress",
                            "selected_candidate_eligible": False,
                        },
                    },
                }
            ],
            most_recent_terminal={},
            agent_summaries={},
            fetch_campaign_detail=lambda campaign_id: {},
        )

        self.assertEqual(summary["status"], "no_selected_candidate")
        self.assertFalse(summary["candidate_available"])
        self.assertEqual(summary["source"], "active_campaign")
        self.assertEqual(summary["best_candidate"], None)

    def test_paper_trade_entry_gate_blocks_without_promoted_candidate(self) -> None:
        catalog_output_dir = self.temp_root / "catalog"

        gate = build_paper_trade_entry_gate(catalog_output_dir)

        self.assertEqual(gate["status"], "blocked")
        self.assertEqual(gate["block_reasons"][0]["code"], "no_promoted_candidate")

    def test_paper_trade_entry_gate_accepts_explicit_promoted_target(self) -> None:
        catalog_output_dir = self.temp_root / "catalog"

        gate = build_paper_trade_entry_gate(
            catalog_output_dir,
            explicit_target={
                "config_path": "configs/eodhd_momentum_broad_candidate_refine_n4_ms002_rf63.toml",
                "profile_name": "candidate-profile",
                "profile_version": "2026-03-23.1",
                "strategy_name": "cross_sectional_momentum",
                "promoted": True,
                "frozen_on": "2026-03-23",
            },
        )

        self.assertEqual(gate["status"], "ready")
        self.assertEqual(gate["recommended_action"], "run_paper_trade_rehearsal")
