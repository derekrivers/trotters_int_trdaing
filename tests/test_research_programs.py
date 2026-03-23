from pathlib import Path
import unittest

from trotters_trader.catalog import load_catalog_entries
from trotters_trader.research_programs import build_research_program_summary, load_research_program_definition, write_research_program_artifacts
from tests.support import IsolatedWorkspaceTestCase


class ResearchProgramTests(IsolatedWorkspaceTestCase):
    def test_research_program_summary_is_active_when_final_step_has_not_run(self) -> None:
        output_dir = self.temp_root / "catalog"
        output_dir.mkdir(parents=True, exist_ok=True)
        history_dir = output_dir / "profile_history"
        history_dir.mkdir(parents=True, exist_ok=True)
        (history_dir / "risk_seed_profile.jsonl").write_text(
            '{"eligible": false, "recommended_action": "retain", "fail_reasons": ["validation_not_pass"]}\n',
            encoding="utf-8",
        )

        definition = {
            "program_id": "risk_sector_program",
            "campaign_path": [
                {
                    "step_id": "risk_seed",
                    "label": "Risk Seed",
                    "profile_name": "risk_seed_profile",
                    "config_path": "configs/risk.toml",
                    "purpose": "seed",
                },
                {
                    "step_id": "sector_follow_up",
                    "label": "Sector Follow-Up",
                    "profile_name": "sector_profile",
                    "config_path": "configs/sector.toml",
                    "purpose": "follow-up",
                },
            ],
        }

        summary = build_research_program_summary(output_dir=output_dir, definition=definition)

        self.assertEqual(summary["status"], "active")
        self.assertEqual(summary["decision"]["recommended_action"], "run_next_step")

    def test_research_program_artifacts_retire_branch_after_terminal_failure(self) -> None:
        output_dir = self.temp_root / "catalog"
        output_dir.mkdir(parents=True, exist_ok=True)
        history_dir = output_dir / "profile_history"
        history_dir.mkdir(parents=True, exist_ok=True)
        (history_dir / "risk_seed_profile.jsonl").write_text(
            '{"eligible": false, "recommended_action": "retain", "fail_reasons": ["validation_not_pass"]}\n',
            encoding="utf-8",
        )
        (history_dir / "sector_profile.jsonl").write_text(
            (
                '{"eligible": false, "recommended_action": "retain", "fail_reasons": '
                '["walkforward_evidence_insufficient", "holdout_not_pass"]}\n'
            ),
            encoding="utf-8",
        )

        definition = {
            "program_id": "risk_sector_program",
            "title": "Risk Sector Program",
            "strategy_family": "cross_sectional_momentum",
            "objective": "test branch",
            "branch_rationale": "best branch",
            "positive_hypotheses": ["holdout should improve"],
            "campaign_path": [
                {
                    "step_id": "risk_seed",
                    "label": "Risk Seed",
                    "profile_name": "risk_seed_profile",
                    "config_path": "configs/risk.toml",
                    "purpose": "seed",
                },
                {
                    "step_id": "sector_follow_up",
                    "label": "Sector Follow-Up",
                    "profile_name": "sector_profile",
                    "config_path": "configs/sector.toml",
                    "purpose": "follow-up",
                },
            ],
            "stop_conditions": [
                {"decision": "retire_branch", "when": "final step fails"}
            ],
        }

        payload = write_research_program_artifacts(output_dir=output_dir, definition=definition)

        self.assertEqual(payload["summary"]["status"], "retired")
        self.assertEqual(payload["summary"]["decision"]["recommended_action"], "retire_branch")
        self.assertTrue(Path(payload["artifacts"]["research_program_json"]).exists())
        self.assertTrue(Path(payload["artifacts"]["research_program_md"]).exists())
        entries = load_catalog_entries(output_dir)
        self.assertTrue(any(entry.get("artifact_type") == "research_program" for entry in entries))

    def test_program_definition_file_loads(self) -> None:
        definition = load_research_program_definition(Path("configs/research_programs/risk_sector_promotion.json"))

        self.assertEqual(definition["program_id"], "risk_sector_promotion_program")
        self.assertEqual(len(definition["campaign_path"]), 2)

    def test_refine_seed_program_definition_file_loads(self) -> None:
        definition = load_research_program_definition(Path("configs/research_programs/refine_seed_continuation.json"))

        self.assertEqual(definition["program_id"], "refine_seed_continuation_program")
        self.assertEqual(definition["campaign_path"][0]["profile_name"], "momentum_broad_candidate_refine_n4_ms002_rf63")

    def test_new_continuity_program_definition_files_load(self) -> None:
        expected = {
            "configs/research_programs/default_broad_operability.json": ("default_broad_operability_program", 2),
            "configs/research_programs/mean_reversion_broad_residual_cap.json": ("mean_reversion_broad_residual_cap_program", 1),
            "configs/research_programs/mean_reversion_broad_volatility_cap.json": ("mean_reversion_broad_volatility_cap_program", 1),
            "configs/research_programs/sma_cross_broad_trend_guard.json": ("sma_cross_broad_trend_guard_program", 1),
            "configs/research_programs/momentum_beta_bucket_guard.json": ("momentum_beta_bucket_guard_program", 1),
            "configs/research_programs/momentum_drawdown_patience_guard.json": ("momentum_drawdown_patience_guard_program", 1),
            "configs/research_programs/momentum_total_return_starter_guard.json": ("momentum_total_return_starter_guard_program", 1),
        }

        for path, (program_id, campaign_count) in expected.items():
            definition = load_research_program_definition(Path(path))
            self.assertEqual(definition["program_id"], program_id)
            self.assertEqual(len(definition["campaign_path"]), campaign_count)


if __name__ == "__main__":
    unittest.main()

