from __future__ import annotations

import unittest

from trotters_trader.active_branch import build_active_branch_summary, launch_claim_is_stale


class ActiveBranchTests(unittest.TestCase):
    def test_build_active_branch_summary_reports_stage_counts(self) -> None:
        payload = build_active_branch_summary(
            active_directors=[
                {
                    "director_id": "director-1",
                    "director_name": "beta-defensive-director",
                    "status": "running",
                    "current_campaign_id": "campaign-1",
                    "state": {"plan_name": "beta_defensive_continuation"},
                    "updated_at": "2026-03-23T10:30:00+00:00",
                }
            ],
            active_campaigns=[
                {
                    "campaign_id": "campaign-1",
                    "director_id": "director-1",
                    "campaign_name": "beta-defensive-primary",
                    "status": "running",
                    "phase": "stability_pivot",
                    "updated_at": "2026-03-23T10:31:00+00:00",
                    "jobs": [
                        {"job_id": "job-1", "status": "running"},
                        {"job_id": "job-2", "status": "queued"},
                        {"job_id": "job-3", "status": "completed"},
                    ],
                    "events": [{"event_type": "campaign_progress", "recorded_at_utc": "2026-03-23T10:31:00+00:00"}],
                }
            ],
        )

        self.assertEqual(payload["status"], "active")
        self.assertEqual(payload["recommended_action"], "wait_for_stage_jobs")
        self.assertEqual(payload["director"]["plan_name"], "beta_defensive_continuation")
        self.assertEqual(payload["campaign"]["campaign_name"], "beta-defensive-primary")
        self.assertEqual(payload["job_counts"]["running"], 1)
        self.assertEqual(payload["job_counts"]["queued"], 1)
        self.assertEqual(payload["job_counts"]["completed"], 1)

    def test_build_active_branch_summary_warns_on_duplicate_campaigns(self) -> None:
        payload = build_active_branch_summary(
            active_directors=[
                {
                    "director_id": "director-1",
                    "director_name": "beta-defensive-director",
                    "status": "running",
                    "current_campaign_id": "campaign-2",
                    "state": {"plan_name": "beta_defensive_continuation"},
                }
            ],
            active_campaigns=[
                {"campaign_id": "campaign-1", "director_id": "director-1", "campaign_name": "beta-defensive-primary", "status": "running", "phase": "benchmark_pivot"},
                {"campaign_id": "campaign-2", "director_id": "director-1", "campaign_name": "beta-defensive-primary", "status": "running", "phase": "stability_pivot"},
            ],
        )

        self.assertEqual(payload["recommended_action"], "inspect_active_branch")
        self.assertEqual(payload["warnings"][0]["code"], "duplicate_active_campaigns")

    def test_launch_claim_is_stale_flags_old_timestamp(self) -> None:
        self.assertFalse(launch_claim_is_stale("2999-03-23T10:00:00+00:00"))
        self.assertTrue(launch_claim_is_stale("2026-03-23T08:00:00+00:00"))


if __name__ == "__main__":
    unittest.main()
