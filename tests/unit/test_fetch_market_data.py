import unittest

from scripts import fetch_market_data as market_data


def candles(count: int = 80, growth: float = 0.002) -> list[market_data.Candle]:
    result = []
    close = 100.0
    for index in range(count):
        close *= 1 + growth + (0.001 if index % 3 == 0 else -0.0005)
        result.append(market_data.Candle(1_700_000_000 + index * 86_400, close - 0.2, close + 0.5, close - 0.5, close, 1000.0))
    return result


class HistoryParsingTest(unittest.TestCase):
    def test_parses_valid_rows_and_skips_missing_rows(self) -> None:
        payload = {
            "chart": {"result": [{
                "timestamp": list(range(1, 23)),
                "indicators": {"quote": [{
                    "open": [10.0] * 21 + [None],
                    "high": [11.0] * 22,
                    "low": [9.0] * 22,
                    "close": [10.5] * 22,
                    "volume": [100] * 21 + [None],
                }]},
            }]}
        }

        parsed = market_data.parse_history(payload, "TEST")

        self.assertEqual(len(parsed), 21)
        self.assertEqual(parsed[0].timestamp, 1)
        self.assertEqual(parsed[0].volume, 100.0)

    def test_rejects_incomplete_response(self) -> None:
        with self.assertRaisesRegex(ValueError, "No daily history"):
            market_data.parse_history({"chart": {"result": []}}, "TEST")

    def test_rejects_too_few_usable_rows(self) -> None:
        payload = {"chart": {"result": [{"timestamp": [1], "indicators": {"quote": [{
            "open": [1], "high": [1], "low": [1], "close": [None]
        }]}}]}}
        with self.assertRaisesRegex(ValueError, "Insufficient daily history"):
            market_data.parse_history(payload, "TEST")


class FeatureAndPredictionTest(unittest.TestCase):
    def test_calculates_expected_features(self) -> None:
        history = [market_data.Candle(index, value, value, value, value, None) for index, value in enumerate(range(100, 121))]

        features = market_data.calculate_features(history)

        self.assertAlmostEqual(features.return_1d, 120 / 119 - 1)
        self.assertAlmostEqual(features.return_5d, 120 / 115 - 1)
        self.assertAlmostEqual(features.return_20d, 0.2)
        self.assertAlmostEqual(features.ma_deviation_5d, 120 / 118 - 1)
        self.assertAlmostEqual(features.ma_deviation_20d, 120 / 110.5 - 1)
        self.assertGreater(features.volatility_5d, 0)
        self.assertGreater(features.volatility_20d, 0)

    def test_prediction_bounds_range_and_labels(self) -> None:
        prediction = market_data.build_prediction(candles())

        self.assertGreaterEqual(prediction["up_probability"], 0)
        self.assertLessEqual(prediction["up_probability"], 1)
        self.assertGreaterEqual(prediction["confidence"], 0)
        self.assertLessEqual(prediction["confidence"], 1)
        self.assertLess(prediction["range_low"], prediction["current"])
        self.assertLess(prediction["current"], prediction["range_high"])
        self.assertEqual(prediction["weather"], "sunny")
        self.assertEqual(prediction["risk"], "calm")

    def test_weather_and_risk_thresholds(self) -> None:
        self.assertEqual([market_data.weather_for_probability(value) for value in (0.7, 0.6, 0.5, 0.4)],
                         ["sunny", "partly_cloudy", "cloudy", "rainy"])
        self.assertEqual([market_data.risk_for_volatility(value) for value in (0.005, 0.01, 0.02, 0.03)],
                         ["calm", "normal", "caution", "storm"])


if __name__ == "__main__":
    unittest.main()
