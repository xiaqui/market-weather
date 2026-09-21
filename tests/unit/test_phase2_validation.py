import unittest

from scripts import fetch_market_data as market_data
from scripts import validate_phase2


def record(timestamp: int, trend: float, analog: float, actual_up: bool):
    return market_data.BacktestRecord(
        timestamp=timestamp,
        trend_probability=trend,
        analog_probability=analog,
        ensemble_probability=(trend + analog) / 2,
        actual_up=actual_up,
        analog_count=30,
        analog_mean_distance=float(timestamp),
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


if __name__ == "__main__":
    unittest.main()
