import unittest
from unittest.mock import patch

from scripts import fetch_market_data as market_data


class BacktestRegressionTest(unittest.TestCase):
    def test_each_prediction_sees_only_rows_before_target(self) -> None:
        candles = [market_data.Candle(i, 100 + i, 101 + i, 99 + i, 100 + i, None) for i in range(25)]
        seen_lengths = []

        def prediction(history):
            seen_lengths.append(len(history))
            return {"up_probability": 1.0}

        with patch.object(market_data, "build_prediction", side_effect=prediction):
            correct, samples, accuracy = market_data.backtest(candles)

        self.assertEqual(seen_lengths, [21, 22, 23, 24])
        self.assertEqual((correct, samples, accuracy), (4, 4, 1.0))


if __name__ == "__main__":
    unittest.main()
