import unittest
from unittest.mock import patch

from scripts import fetch_market_data as market_data


class BacktestRegressionTest(unittest.TestCase):
    def test_in_progress_daily_candle_is_excluded(self) -> None:
        session_start = 2_000_000
        completed_timestamps = list(range(1, 22))
        timestamps = completed_timestamps + [session_start]
        payload = {
            "chart": {"result": [{
                "meta": {"currentTradingPeriod": {"regular": {
                    "start": session_start,
                    "end": session_start + 10_000,
                }}},
                "timestamp": timestamps,
                "indicators": {"quote": [{
                    "open": [100.0] * 22,
                    "high": [101.0] * 22,
                    "low": [99.0] * 22,
                    "close": [100.0] * 21 + [150.0],
                    "volume": [1000] * 22,
                }]},
            }]}
        }

        parsed = market_data.parse_history(
            payload, "TEST", now_timestamp=session_start + 100
        )

        self.assertEqual([candle.timestamp for candle in parsed], completed_timestamps)
        self.assertEqual(parsed[-1].close, 100.0)

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
