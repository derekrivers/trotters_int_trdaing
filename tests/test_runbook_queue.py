from __future__ import annotations

import unittest
from unittest.mock import patch

from trotters_trader.runbook_queue import build_runbook_queue_summary


class RunbookQueueTests(unittest.TestCase):
    def test_build_runbook_queue_summary_flags_untracked_active_plan_and_retired_followups(self) -> None:
        with patch(
            "trotters_trader.runbook_queue._load_runbook",
            return_value={
                "work_queue": [
                    {"plan_id": "broad_operability", "director_name": "broad-operability-director", "enabled": True, "priority": 1},
                    {"plan_id": "beta_defensive_continuation", "director_name": "beta-defensive-director", "enabled": True, "priority": 2},
                ]
            },
        ):
            summary = build_runbook_queue_summary(
                active_branch_summary={"director": {"plan_name": "broad_operability"}},
                research_program_portfolio={
                    "programs": [
                        {
                            "queue_plan_id": "beta_defensive_continuation",
                            "title": "Beta-Defensive Continuation Program",
                            "status": "retired",
                            "decision_summary": "Retired after terminal failure.",
                        }
                    ]
                },
                research_family_comparison_summary={
                    "families": [
                        {
                            "plan_id": "beta_defensive_continuation",
                            "proposal_id": "beta_defensive_continuation",
                            "approval_status": "approved",
                            "family_status": "queued",
                        }
                    ]
                },
            )

        self.assertEqual(summary["summary_type"], "runbook_queue_summary")
        self.assertEqual(summary["entries"][0]["queue_status"], "active")
        self.assertEqual(summary["entries"][1]["queue_status"], "blocked_retired")
        warning_codes = {warning["code"] for warning in summary["warnings"]}
        self.assertIn("active_plan_untracked", warning_codes)
        self.assertIn("enabled_retired_program", warning_codes)
        self.assertEqual(summary["recommended_action"], "repair_runbook_alignment")

    def test_build_runbook_queue_summary_identifies_next_runnable_plan(self) -> None:
        with patch(
            "trotters_trader.runbook_queue._load_runbook",
            return_value={
                "work_queue": [
                    {"plan_id": "broad_operability", "director_name": "broad-operability-director", "enabled": True, "priority": 1},
                    {"plan_id": "next_family", "director_name": "next-family-director", "enabled": True, "priority": 2},
                ]
            },
        ):
            summary = build_runbook_queue_summary(
                active_branch_summary={"director": {"plan_name": "broad_operability"}},
                research_program_portfolio={
                    "programs": [
                        {
                            "queue_plan_id": "next_family",
                            "title": "Next Family Program",
                            "status": "active",
                        }
                    ]
                },
                research_family_comparison_summary={
                    "families": [
                        {
                            "plan_id": "next_family",
                            "proposal_id": "next_family",
                            "approval_status": "approved",
                            "family_status": "queued",
                        }
                    ]
                },
            )

        self.assertEqual(summary["status"], "attention")
        self.assertEqual(summary["next_runnable_plan_id"], "next_family")
        self.assertEqual(summary["entries"][1]["queue_status"], "ready")

    def test_build_runbook_queue_summary_requests_start_when_no_plan_is_active(self) -> None:
        with patch(
            "trotters_trader.runbook_queue._load_runbook",
            return_value={
                "work_queue": [
                    {"plan_id": "approved_family", "director_name": "approved-family-director", "enabled": True, "priority": 1},
                ]
            },
        ):
            summary = build_runbook_queue_summary(
                active_branch_summary={},
                research_program_portfolio={
                    "programs": [
                        {
                            "queue_plan_id": "approved_family",
                            "title": "Approved Family Program",
                            "status": "active",
                        }
                    ]
                },
                research_family_comparison_summary={
                    "families": [
                        {
                            "plan_id": "approved_family",
                            "proposal_id": "approved_family",
                            "approval_status": "approved",
                            "family_status": "queued",
                        }
                    ]
                },
            )

        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["next_runnable_plan_id"], "approved_family")
        self.assertEqual(summary["recommended_action"], "start_approved_family")
        self.assertEqual(summary["continuity_status"], "low")
        self.assertEqual(summary["standby_ready_depth"], 1)

    def test_build_runbook_queue_summary_stays_aligned_when_last_active_plan_has_no_followup(self) -> None:
        with patch(
            "trotters_trader.runbook_queue._load_runbook",
            return_value={
                "work_queue": [
                    {"plan_id": "approved_family", "director_name": "approved-family-director", "enabled": True, "priority": 1},
                ]
            },
        ):
            summary = build_runbook_queue_summary(
                active_branch_summary={"director": {"plan_name": "approved_family"}},
                research_program_portfolio={
                    "programs": [
                        {
                            "queue_plan_id": "approved_family",
                            "title": "Approved Family Program",
                            "status": "active",
                        }
                    ]
                },
                research_family_comparison_summary={
                    "families": [
                        {
                            "plan_id": "approved_family",
                            "proposal_id": "approved_family",
                            "approval_status": "approved",
                            "family_status": "active",
                        }
                    ]
                },
            )

        self.assertEqual(summary["status"], "aligned")
        self.assertEqual(summary["next_runnable_plan_id"], None)
        self.assertEqual(summary["recommended_action"], "monitor_active_plan")
        self.assertEqual(summary["continuity_status"], "empty")
        warning_codes = {warning["code"] for warning in summary["warnings"]}
        self.assertNotIn("no_next_runnable_queue_item", warning_codes)

    def test_build_runbook_queue_summary_does_not_treat_untracked_entries_as_runnable(self) -> None:
        with patch(
            "trotters_trader.runbook_queue._load_runbook",
            return_value={
                "work_queue": [
                    {"plan_id": "broad_operability", "director_name": "broad-operability-director", "enabled": True, "priority": 1},
                    {"plan_id": "unknown_followup", "director_name": "unknown-followup-director", "enabled": True, "priority": 2},
                ]
            },
        ):
            summary = build_runbook_queue_summary(
                active_branch_summary={"director": {"plan_name": "broad_operability"}},
                research_program_portfolio={"programs": []},
                research_family_comparison_summary={},
            )

        self.assertIsNone(summary["next_runnable_plan_id"])
        self.assertEqual(summary["recommended_action"], "repair_runbook_alignment")
        warning_codes = {warning["code"] for warning in summary["warnings"]}
        self.assertIn("enabled_untracked_plan", warning_codes)
        self.assertIn("active_plan_untracked", warning_codes)

    def test_build_runbook_queue_summary_blocks_unapproved_family(self) -> None:
        with patch(
            "trotters_trader.runbook_queue._load_runbook",
            return_value={
                "work_queue": [
                    {"plan_id": "approved_family", "director_name": "approved-family-director", "enabled": True, "priority": 1},
                ]
            },
        ):
            summary = build_runbook_queue_summary(
                active_branch_summary={},
                research_program_portfolio={
                    "programs": [
                        {
                            "queue_plan_id": "approved_family",
                            "title": "Approved Family Program",
                            "status": "active",
                        }
                    ]
                },
                research_family_comparison_summary={
                    "families": [
                        {
                            "plan_id": "approved_family",
                            "proposal_id": "approved_family",
                            "approval_status": "under_review",
                            "family_status": "under_review",
                        }
                    ]
                },
            )

        self.assertEqual(summary["entries"][0]["queue_status"], "blocked_pending_approval")
        self.assertEqual(summary["recommended_action"], "approve_research_family")

    def test_build_runbook_queue_summary_reports_healthy_continuity_for_multi_item_backlog(self) -> None:
        with patch(
            "trotters_trader.runbook_queue._load_runbook",
            return_value={
                "work_queue": [
                    {"plan_id": "alpha_family", "director_name": "alpha-family-director", "enabled": True, "priority": 1},
                    {"plan_id": "beta_family", "director_name": "beta-family-director", "enabled": True, "priority": 2},
                    {"plan_id": "gamma_family", "director_name": "gamma-family-director", "enabled": True, "priority": 3},
                ]
            },
        ):
            summary = build_runbook_queue_summary(
                active_branch_summary={"director": {"plan_name": "alpha_family"}},
                research_program_portfolio={
                    "programs": [
                        {"queue_plan_id": "alpha_family", "title": "Alpha Family Program", "status": "active"},
                        {"queue_plan_id": "beta_family", "title": "Beta Family Program", "status": "active"},
                        {"queue_plan_id": "gamma_family", "title": "Gamma Family Program", "status": "active"},
                    ]
                },
                research_family_comparison_summary={
                    "families": [
                        {"plan_id": "alpha_family", "proposal_id": "alpha_family", "approval_status": "approved", "family_status": "queued"},
                        {"plan_id": "beta_family", "proposal_id": "beta_family", "approval_status": "approved", "family_status": "queued"},
                        {"plan_id": "gamma_family", "proposal_id": "gamma_family", "approval_status": "approved", "family_status": "queued"},
                    ]
                },
            )

        self.assertEqual(summary["continuity_status"], "healthy")
        self.assertEqual(summary["standby_ready_depth"], 2)
        self.assertEqual(summary["standby_ready_plan_ids"], ["beta_family", "gamma_family"])


if __name__ == "__main__":
    unittest.main()
