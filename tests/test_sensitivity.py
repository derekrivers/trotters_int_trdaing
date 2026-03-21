from pathlib import Path
import unittest

from trotters_trader.canonical import materialize_canonical_data
from trotters_trader.experiments import run_sensitivity_matrix
from tests.support import IsolatedWorkspaceTestCase


class SensitivityTests(IsolatedWorkspaceTestCase):
    def test_sensitivity_matrix_runs_multiple_scenarios(self) -> None:
        config = self.isolated_config(Path("configs/backtest.toml"))
        materialize_canonical_data(config.data)
        results = run_sensitivity_matrix(config)

        self.assertEqual(len(results), 32)
        self.assertTrue(all("ending_nav" in result.summary for result in results))


if __name__ == "__main__":
    unittest.main()
