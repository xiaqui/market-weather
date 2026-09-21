import unittest

from scripts import fetch_market_data as market_data
from scripts import validate_phase2


def record(
    timestamp: int,
    trend: float,
    analog: float,
    actual_up: bool,
    historical_up: float = 0.5,
):
    return market_data.BacktestRecord(
        timestamp=timestamp,
        trend_probability=trend,
        analog_probability=analog,
        ensemble_probability=(trend + analog) / 2,
        actual_up=actual_up,
        analog_count=30,
        analog_mean_distance=float(timestamp),
        historical_up_probability=historical_up,
    )


class Phase2ValidationTest(unittest.TestCase):
    def test_windows_are_fixed_size_non_overlapping_and_discovery_is_latest(self):
        records = [record(index, 0.6, 0.7, True) for index in range(1260)]

        windows = validate_phase2.split_windows(records)

        self.assertEqual([len(window) for window in windows], [252] * 5)
        self.assertEqual((windows[0][0].timestamp, windows[0][-1].timestamp), (1008, 1259))
        timestamps = [{item.timestamp for item in window} for window in windows]
        for left_index, left in enumerate(timestamps):
            for right in timestamps[left_index + 1:]:
                self.assertTrue(left.isdisjoint(right))

    def test_paired_counts_cover_samples_and_disagreement(self):
        records = [
            record(1, 0.7, 0.8, True),
            record(2, 0.7, 0.4, True),
            record(3, 0.4, 0.7, True),
            record(4, 0.3, 0.2, True),
        ]

        report = validate_phase2.describe_window(records)

        self.assertEqual(sum(report["paired"].values()), len(records))
        self.assertEqual(
            sum(report["disagreement_paired"].values()),
            report["disagreement"]["sample_count"],
        )

    def test_wilson_interval_matches_known_fixture(self):
        lower, upper = validate_phase2.wilson_interval(5, 10)

        self.assertAlmostEqual(lower, 0.236593, places=6)
        self.assertAlmostEqual(upper, 0.763407, places=6)
        self.assertIsNone(validate_phase2.wilson_interval(0, 0))

    def test_exact_paired_test_is_two_sided(self):
        self.assertEqual(validate_phase2.exact_paired_p_value(0, 4), 0.125)
        self.assertEqual(validate_phase2.exact_paired_p_value(2, 2), 1.0)
        self.assertIsNone(validate_phase2.exact_paired_p_value(0, 0))

    def test_naive_baselines_use_predictions_recorded_before_each_outcome(self):
        records = [
            record(1, 0.7, 0.8, True, historical_up=0.6),
            record(2, 0.7, 0.8, False, historical_up=0.7),
            record(3, 0.7, 0.8, True, historical_up=0.4),
            record(4, 0.7, 0.8, True, historical_up=0.3),
        ]

        baselines = validate_phase2.describe_window(records)["naive_baselines"]

        self.assertEqual(baselines["always_up_accuracy"], 0.75)
        self.assertEqual(baselines["always_down_accuracy"], 0.25)
        self.assertEqual(baselines["constant_50_brier"], 0.25)
        self.assertEqual(baselines["expanding_historical_up_rate"]["accuracy"], 0.25)
        self.assertAlmostEqual(
            baselines["expanding_historical_up_rate"]["brier"],
            (0.16 + 0.49 + 0.36 + 0.49) / 4,
        )


if __name__ == "__main__":
    unittest.main()
