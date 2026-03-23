from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from trotters_trader.research_families import (
    build_next_family_status,
    build_research_family_comparison_summary,
    bootstrap_research_family,
    load_research_family_proposal_definition,
)
from tests.support import IsolatedWorkspaceTestCase


class ResearchFamilyTests(IsolatedWorkspaceTestCase):
    def test_research_family_comparison_summary_loads_current_approved_family(self) -> None:
        summary = build_research_family_comparison_summary(catalog_output_dir=self.temp_root / "catalog")

        self.assertEqual(summary["summary_type"], "research_family_comparison_summary")
        self.assertEqual(summary["current_proposal"]["proposal_id"], "mean_reversion_broad_reentry")
        self.assertIn(summary["current_proposal"]["family_status"], {"approved", "queued", "active"})

    def test_next_family_status_blocks_when_only_unapproved_family_exists(self) -> None:
        with patch(
            "trotters_trader.research_families.load_research_family_proposals",
            return_value=[
                {
                    "proposal_id": "quality_under_review",
                    "title": "Quality Family",
                    "strategy_family": "quality",
                    "hypothesis": "quality overlay",
                    "why_different_from_retired": ["different engine"],
                    "success_criteria": ["pass policy"],
                    "stop_conditions": [{"decision": "retire_branch", "when": "fails"}],
                    "approval_status": "under_review",
                    "novelty_vs_retired": "material",
                    "implementation_readiness": "planned",
                    "expected_evidence_cost": "medium",
                    "promotion_path_compatibility": "compatible",
                    "bootstrap": {"plan_id": "quality_family", "program_id": "quality_family_program"},
                    "_proposal_path": "configs/research_family_proposals/quality_under_review.json",
                }
            ],
        ):
            family_summary = build_research_family_comparison_summary(catalog_output_dir=self.temp_root / "catalog")
            next_family = build_next_family_status(
                catalog_output_dir=self.temp_root / "catalog",
                runbook_queue_summary={"recommended_action": "define_next_research_family"},
                research_family_comparison_summary=family_summary,
                active_branch_summary=None,
            )

        self.assertEqual(next_family["status"], "blocked_pending_approval")
        self.assertEqual(next_family["recommended_action"], "approve_research_family")

    def test_bootstrap_research_family_materializes_program_and_director_files(self) -> None:
        repo_root = self.temp_root / "repo"
        (repo_root / "configs" / "openclaw").mkdir(parents=True, exist_ok=True)
        (repo_root / "configs" / "research_family_proposals").mkdir(parents=True, exist_ok=True)
        (repo_root / "configs" / "directors").mkdir(parents=True, exist_ok=True)
        (repo_root / "configs" / "research_programs").mkdir(parents=True, exist_ok=True)
        (repo_root / "configs" / "openclaw" / "trotters-runbook.json").write_text(
            json.dumps({"version": 1, "work_queue": []}, indent=2),
            encoding="utf-8",
        )
        proposal_path = repo_root / "configs" / "research_family_proposals" / "approved_family.json"
        proposal_path.write_text(
            json.dumps(
                {
                    "proposal_id": "approved_family",
                    "title": "Approved Family",
                    "strategy_family": "mean_reversion",
                    "hypothesis": "materially different",
                    "why_different_from_retired": ["different signal family"],
                    "success_criteria": ["pass promotion policy"],
                    "stop_conditions": [{"decision": "retire_branch", "when": "fails"}],
                    "approval_status": "approved",
                    "bootstrap": {
                        "plan_id": "approved_family",
                        "program_id": "approved_family_program",
                        "program_title": "Approved Family Program",
                        "director_name": "approved-family-director",
                        "campaign_name": "approved-family-primary",
                        "config_path": "configs/eodhd_mean_reversion_broad_candidate_n8_ms005_rf21.toml",
                        "campaign_path": [
                            {
                                "step_id": "seed",
                                "label": "Seed",
                                "profile_name": "approved-family-profile",
                                "config_path": "configs/eodhd_mean_reversion_broad_candidate_n8_ms005_rf21.toml",
                                "purpose": "run seed",
                            }
                        ],
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        with patch("trotters_trader.research_families._repo_root", return_value=repo_root):
            result = bootstrap_research_family(
                proposal_id="approved_family",
                catalog_output_dir=self.temp_root / "catalog",
                enable_queue=True,
            )

        self.assertTrue((repo_root / "configs" / "directors" / "approved_family.json").exists())
        self.assertTrue((repo_root / "configs" / "research_programs" / "approved_family.json").exists())
        runbook = json.loads((repo_root / "configs" / "openclaw" / "trotters-runbook.json").read_text(encoding="utf-8"))
        self.assertEqual(runbook["work_queue"][0]["plan_id"], "approved_family")
        self.assertEqual(result["plan_id"], "approved_family")

    def test_load_research_family_proposal_definition_requires_difference_and_stop_conditions(self) -> None:
        proposal_path = self.temp_root / "bad_proposal.json"
        proposal_path.write_text(
            json.dumps(
                {
                    "proposal_id": "bad_family",
                    "title": "Bad Family",
                    "strategy_family": "mean_reversion",
                    "hypothesis": "missing evidence",
                    "why_different_from_retired": [],
                    "success_criteria": ["pass promotion policy"],
                    "stop_conditions": [],
                    "approval_status": "proposed",
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "must explain why it differs from retired work"):
            load_research_family_proposal_definition(proposal_path)
