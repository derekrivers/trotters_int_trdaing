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
            )

        self.assertEqual(summary["status"], "attention")
        self.assertEqual(summary["next_runnable_plan_id"], "next_family")
        self.assertEqual(summary["entries"][1]["queue_status"], "ready")


if __name__ == "__main__":
    unittest.main()
