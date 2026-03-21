from pathlib import Path
import unittest

from trotters_trader.backtest import run_backtest
from trotters_trader.canonical import materialize_canonical_data
from trotters_trader.catalog import load_catalog_entries
from trotters_trader.experiments import run_sma_grid, write_experiment_comparison
from tests.support import IsolatedWorkspaceTestCase


class CatalogTests(IsolatedWorkspaceTestCase):
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


if __name__ == "__main__":
    unittest.main()
