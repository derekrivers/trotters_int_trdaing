import os
import unittest
from unittest.mock import patch

from trotters_trader.cli import _build_parser


class CliTests(unittest.TestCase):
    def test_research_worker_defaults_worker_id_from_hostname(self) -> None:
        with patch.dict(os.environ, {"HOSTNAME": "compose-worker-7"}):
            parser = _build_parser()
            args = parser.parse_args(["research-worker"])

        self.assertEqual(args.worker_id, "worker-compose-worker-7")

    def test_research_worker_falls_back_to_legacy_default_without_hostname(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            parser = _build_parser()
            args = parser.parse_args(["research-worker"])

        self.assertEqual(args.worker_id, "worker-01")

    def test_parser_accepts_operability_program_command(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["operability-program"])

        self.assertEqual(args.command, "operability-program")

    def test_parser_accepts_research_campaign_start_command(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["research-campaign-start"])

        self.assertEqual(args.command, "research-campaign-start")

    def test_parser_accepts_research_campaign_stop_command(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["research-campaign-stop", "--campaign-id", "campaign-1"])

        self.assertEqual(args.command, "research-campaign-stop")
        self.assertEqual(args.campaign_id, "campaign-1")

    def test_parser_accepts_campaign_notification_options(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(
            [
                "research-campaign-start",
                "--notification-command",
                "echo notify",
                "--notify-events",
                "campaign_finished,campaign_failed",
            ]
        )

        self.assertEqual(args.notification_command, "echo notify")
        self.assertEqual(args.notify_events, "campaign_finished,campaign_failed")


if __name__ == "__main__":
    unittest.main()
