from pathlib import Path
import unittest

from trotters_trader.canonical import materialize_canonical_data
from trotters_trader.experiments import run_threshold_sweep
from tests.support import IsolatedWorkspaceTestCase


class ThresholdSweepTests(IsolatedWorkspaceTestCase):
    def test_threshold_sweep_runs_expected_number_of_scenarios(self) -> None:
        config = self.isolated_config(Path("configs/backtest.toml"))
        materialize_canonical_data(config.data)
        results = run_threshold_sweep(config)

        self.assertEqual(len(results), 9)
        self.assertTrue(all("ending_nav" in result.summary for result in results))


if __name__ == "__main__":
    unittest.main()
