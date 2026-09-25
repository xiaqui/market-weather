import unittest

from scripts import fetch_market_data as market_data


def record(
    trend: float,
    analog: float | None,
    actual_up: bool,
    distance: float | None = 1.0,
    confidence: float = 0.7,
) -> market_data.BacktestRecord:
    ensemble = trend if analog is None else (trend + analog) / 2
    return market_data.BacktestRecord(
        timestamp=1,
        trend_probability=trend,
        analog_probability=analog,
        ensemble_probability=ensemble,
        actual_up=actual_up,
        analog_count=0 if analog is None else 30,
        analog_mean_distance=None if analog is None else distance,
        confidence=confidence,
    )


class BacktestDiagnosticsTest(unittest.TestCase):
    def test_four_direction_groups_and_agreement_are_classified(self) -> None:
        records = [
            record(0.6, 0.7, True),
            record(0.6, 0.4, False),
            record(0.4, 0.6, True),
            record(0.4, 0.3, False),
        ]

        diagnostics = market_data.build_backtest_diagnostics(records)

        self.assertEqual(
            [group["sample_count"] for group in diagnostics["direction_groups"].values()],
            [1, 1, 1, 1],
        )
        self.assertEqual(diagnostics["agreement"]["sample_count"], 2)
        self.assertEqual(diagnostics["disagreement"]["sample_count"], 2)
        self.assertEqual(diagnostics["agreement"]["ensemble_accuracy"], 1.0)
        self.assertEqual(diagnostics["disagreement"]["analog_accuracy"], 1.0)

    def test_combined_strength_and_fixed_bin_boundaries(self) -> None:
        self.assertAlmostEqual(
            market_data.combined_strength(record(0.55, 0.54, True)), 0.09
        )
        self.assertEqual(market_data.strength_bin(0.0999), "weak")
        self.assertEqual(market_data.strength_bin(0.10), "medium")
        self.assertEqual(market_data.strength_bin(0.2499), "medium")
        self.assertEqual(market_data.strength_bin(0.25), "strong")

    def test_distance_tertiles_preserve_every_available_sample(self) -> None:
        records = [
            record(0.6, 0.6, index % 2 == 0, distance=float(index))
            for index in range(1, 11)
        ]

        diagnostics = market_data.build_backtest_diagnostics(records)

        self.assertEqual(
            sum(group["sample_count"] for group in diagnostics["distance_groups"].values()),
            len(records),
        )
        means = [group["mean_distance"] for group in diagnostics["distance_groups"].values()]
        self.assertLess(means[0], means[1])
        self.assertLess(means[1], means[2])

    def test_brier_score_and_missing_analog_are_handled(self) -> None:
        records = [
            record(0.0, 1.0, False),
            record(1.0, 0.0, True),
            record(0.8, None, True),
        ]

        diagnostics = market_data.build_backtest_diagnostics(records)

        self.assertAlmostEqual(diagnostics["brier"]["trend"], (0 + 0 + 0.04) / 3)
        self.assertEqual(diagnostics["brier"]["analog"], 1.0)
        self.assertAlmostEqual(diagnostics["brier"]["ensemble"], (0.25 + 0.25 + 0.04) / 3)
        self.assertEqual(diagnostics["analog_available_count"], 2)
        self.assertEqual(diagnostics["analog_unavailable_count"], 1)
        self.assertEqual(
            sum(group["sample_count"] for group in diagnostics["direction_groups"].values()),
            2,
        )

    def test_confidence_buckets_preserve_every_walk_forward_sample(self) -> None:
        records = [
            record(0.6, 0.7, True, confidence=value)
            for value in (0.2, 0.5, 0.7, 0.9)
        ]

        groups = market_data.build_backtest_diagnostics(records)["confidence_groups"]

        self.assertEqual([group["sample_count"] for group in groups.values()], [1, 1, 1, 1])
        self.assertTrue(all(group["direction_accuracy"] == 1.0 for group in groups.values()))


if __name__ == "__main__":
    unittest.main()
