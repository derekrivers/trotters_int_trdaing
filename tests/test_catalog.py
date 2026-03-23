from pathlib import Path
import unittest
from unittest.mock import patch

from trotters_trader.backtest import run_backtest
from trotters_trader.canonical import materialize_canonical_data
from trotters_trader.catalog import _atomic_write_text, load_catalog_entries
from trotters_trader.experiments import run_sma_grid, write_experiment_comparison
from tests.support import IsolatedWorkspaceTestCase


class CatalogTests(IsolatedWorkspaceTestCase):
    def test_load_catalog_entries_returns_empty_when_file_disappears_during_read(self) -> None:
        output_dir = self.temp_root / "runs"
        catalog_dir = output_dir / "research_catalog"
        catalog_dir.mkdir(parents=True, exist_ok=True)
        jsonl_path = catalog_dir / "catalog.jsonl"
        jsonl_path.write_text('{"artifact_type":"run"}\n', encoding="utf-8")

        with patch("pathlib.Path.read_text", side_effect=FileNotFoundError("catalog swapped during read")):
            entries = load_catalog_entries(output_dir)

        self.assertEqual(entries, [])

    def test_backtest_registers_run_in_catalog(self) -> None:
        config = self.isolated_config(Path("configs/backtest.toml"))
        materialize_canonical_data(config.data)

        run_backtest(config)

        entries = load_catalog_entries(config.run.output_dir)
        self.assertTrue(any(entry.get("artifact_type") == "run" for entry in entries))
        self.assertTrue((config.run.output_dir / "research_catalog" / "latest_profile_artifacts.json").exists())

    def test_comparison_report_writes_research_decision_and_catalog_entries(self) -> None:
        config = self.isolated_config(Path("configs/backtest.toml"))
        materialize_canonical_data(config.data)
        results = run_sma_grid(config)

        outputs = write_experiment_comparison(
            results=results,
            output_dir=config.run.output_dir,
            report_name="catalog_report",
        )

        self.assertTrue(Path(outputs["research_decision_json"]).exists())
        self.assertTrue(Path(outputs["research_decision_md"]).exists())

        entries = load_catalog_entries(config.run.output_dir)
        artifact_types = {entry.get("artifact_type") for entry in entries}
        self.assertIn("comparison_report", artifact_types)
        self.assertIn("research_decision", artifact_types)

    def test_atomic_write_text_retries_permission_error_once(self) -> None:
        target_path = self.temp_root / "catalog.jsonl"
        real_replace = __import__("os").replace
        attempts = {"count": 0}

        def flaky_replace(source, destination):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise PermissionError("locked")
            return real_replace(source, destination)

        with (
            patch("trotters_trader.catalog.os.replace", side_effect=flaky_replace) as replace_mock,
            patch("trotters_trader.catalog.time.sleep") as sleep_mock,
        ):
            _atomic_write_text(target_path, "example\n")

        self.assertEqual(replace_mock.call_count, 2)
        sleep_mock.assert_called_once()
        self.assertEqual(target_path.read_text(encoding="utf-8"), "example\n")


if __name__ == "__main__":
    unittest.main()
