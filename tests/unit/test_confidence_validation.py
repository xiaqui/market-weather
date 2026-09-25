import unittest

from scripts import fetch_market_data as market_data
from scripts import validate_confidence


def record(timestamp: int, confidence: float, correct: bool):
    return market_data.BacktestRecord(
        timestamp=timestamp,
        trend_probability=0.7,
        analog_probability=0.7,
        ensemble_probability=0.7,
        actual_up=correct,
        analog_count=30,
        analog_mean_distance=1.0,
        trend_confidence=confidence,
        confidence=confidence,
        analog_distance_quality=0.8,
    )


class ConfidenceValidationTest(unittest.TestCase):
    def test_train_quantiles_are_applied_to_separate_validation_rows(self):
        train = [record(index, value, True) for index, value in enumerate((0.2, 0.4, 0.6, 0.8))]
        validation = [record(10, 0.1, False), record(11, 0.9, True)]

        result = validate_confidence.evaluate_candidate(
            train, validation, "trend_only"
        )

        self.assertEqual(result["train_quantile_buckets"]["q1"]["count"], 1)
        self.assertEqual(result["train_quantile_buckets"]["q4"]["count"], 1)
        self.assertEqual(result["high_minus_low_accuracy"], 1.0)

    def test_all_required_candidates_are_exposed(self):
        candidates = market_data.confidence_candidates(record(1, 0.7, True))

        self.assertEqual(set(candidates), set(validate_confidence.CANDIDATES))
        self.assertTrue(all(0.0 <= value <= 1.0 for value in candidates.values()))


if __name__ == "__main__":
    unittest.main()
