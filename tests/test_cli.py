import argparse
from datetime import date
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from trotters_trader.cli import _build_parser, _handle_runtime_command, _runtime_target_warning, execute_command
from tests.support import IsolatedWorkspaceTestCase


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

    def test_parser_accepts_paper_trade_decision_command(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(
            [
                "paper-trade-decision",
                "--config",
                "configs/backtest.toml",
                "--reference-date",
                "2026-03-21",
            ]
        )

        self.assertEqual(args.command, "paper-trade-decision")
        self.assertEqual(args.config, "configs/backtest.toml")
        self.assertEqual(str(args.reference_date), "2026-03-21")

    def test_parser_accepts_research_campaign_start_command(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["research-campaign-start"])

        self.assertEqual(args.command, "research-campaign-start")

    def test_parser_accepts_research_campaign_stop_command(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["research-campaign-stop", "--campaign-id", "campaign-1"])

        self.assertEqual(args.command, "research-campaign-stop")
        self.assertEqual(args.campaign_id, "campaign-1")

    def test_parser_accepts_research_director_start_command(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(
            [
                "research-director-start",
                "--config",
                "configs/backtest.toml",
                "--director-name",
                "director-1",
                "--director-plan-file",
                "configs/directors/broad_operability.json",
                "--allow-host-runtime",
            ]
        )

        self.assertEqual(args.command, "research-director-start")
        self.assertEqual(args.config, "configs/backtest.toml")
        self.assertEqual(args.director_name, "director-1")
        self.assertEqual(args.director_plan_file, "configs/directors/broad_operability.json")
        self.assertTrue(args.allow_host_runtime)

    def test_parser_accepts_research_director_stop_command(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["research-director-stop", "--director-id", "director-1", "--stop-active-campaign"])

        self.assertEqual(args.command, "research-director-stop")
        self.assertEqual(args.director_id, "director-1")
        self.assertTrue(args.stop_active_campaign)

    def test_parser_accepts_research_director_pause_resume_and_skip_commands(self) -> None:
        parser = _build_parser()
        pause_args = parser.parse_args(["research-director-pause", "--director-id", "director-1"])
        resume_args = parser.parse_args(["research-director-resume", "--director-id", "director-1"])
        skip_args = parser.parse_args(["research-director-skip-next", "--director-id", "director-1"])

        self.assertEqual(pause_args.command, "research-director-pause")
        self.assertEqual(resume_args.command, "research-director-resume")
        self.assertEqual(skip_args.command, "research-director-skip-next")
        self.assertEqual(skip_args.director_id, "director-1")

    def test_parser_accepts_research_dashboard_command(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["research-dashboard", "--dashboard-port", "9999"])

        self.assertEqual(args.command, "research-dashboard")
        self.assertEqual(args.dashboard_port, 9999)

    def test_parser_accepts_research_api_command(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["research-api", "--api-port", "8891"])

        self.assertEqual(args.command, "research-api")
        self.assertEqual(args.api_port, 8891)

    def test_parser_accepts_research_ops_bridge_command(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["research-ops-bridge", "--ops-port", "8892", "--runbook-file", "configs/openclaw/trotters-runbook.json"])

        self.assertEqual(args.command, "research-ops-bridge")
        self.assertEqual(args.ops_port, 8892)
        self.assertEqual(args.runbook_file, "configs/openclaw/trotters-runbook.json")

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

    def test_runtime_target_warning_detects_local_runtime_when_compose_uses_named_volume(self) -> None:
        warning = _runtime_target_warning(
            "research-director-status",
            "runtime/research_runtime",
            cwd=Path("workspace"),
            compose_text=(
                "services:\n"
                "  coordinator:\n"
                "    volumes:\n"
                "      - research_runtime:/runtime/research_runtime\n"
                "volumes:\n"
                "  research_runtime:\n"
            ),
        )

        self.assertIsNotNone(warning)
        self.assertIn("/runtime/research_runtime", str(warning))

    def test_runtime_target_warning_ignores_container_runtime_path(self) -> None:
        warning = _runtime_target_warning(
            "research-director-status",
            "/runtime/research_runtime",
            cwd=Path("workspace"),
            compose_text=(
                "services:\n"
                "  coordinator:\n"
                "    volumes:\n"
                "      - research_runtime:/runtime/research_runtime\n"
                "volumes:\n"
                "  research_runtime:\n"
            ),
        )

        self.assertIsNone(warning)

    def test_runtime_target_guard_blocks_mutating_commands_against_local_runtime(self) -> None:
        args = argparse.Namespace(
            command="research-director-start",
            runtime_root="runtime/research_runtime",
            catalog_output_dir="runs",
            allow_host_runtime=False,
        )

        with patch(
            "trotters_trader.cli._runtime_target_warning",
            return_value="wrong runtime target",
        ):
            with self.assertRaisesRegex(ValueError, "wrong runtime target"):
                _handle_runtime_command(args)


class CliCommandExecutionTests(IsolatedWorkspaceTestCase):
    def test_execute_command_writes_paper_trade_decision_artifacts(self) -> None:
        config = self.isolated_config(Path("configs/backtest.toml"))

        payload = execute_command(
            "paper-trade-decision",
            config,
            "configs/backtest.toml",
            scope_data_paths=False,
            prepare_data=True,
            command_args=argparse.Namespace(reference_date=date(2026, 3, 21)),
        )

        self.assertIn("decision_package", payload)
        self.assertIn("artifacts", payload)
        self.assertTrue(Path(payload["artifacts"]["decision_json"]).exists())
        self.assertTrue(Path(payload["artifacts"]["decision_md"]).exists())
        self.assertTrue(Path(payload["artifacts"]["targets_csv"]).exists())
        warnings = payload["decision_package"].get("warnings", [])
        self.assertTrue(any("rehearsal" in str(warning).lower() for warning in warnings))
        self.assertTrue(any("stale" in str(warning).lower() for warning in warnings))


if __name__ == "__main__":
    unittest.main()
