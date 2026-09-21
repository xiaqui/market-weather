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

    def test_asof_join_uses_latest_available_row_not_same_array_index(self) -> None:
        def rows(skip_timestamp=None):
            result = []
            for index in range(30):
                timestamp = 1000 + index * 100
                if timestamp == skip_timestamp:
                    continue
                close = 100 + index
                result.append(market_data.Candle(timestamp, close, close, close, close, None))
            return result

        histories = {market: rows() for market in market_data.MARKET_ORDER}
        histories["dow"] = rows(skip_timestamp=3700)
        # A future, extreme row must not affect the state at timestamp 3700.
        histories["gold"].append(market_data.Candle(9999, 9999, 9999, 9999, 9999, None))

        state = market_data.weather_map_at(histories, 3700)
        truncated = {
            market: [row for row in values if row.timestamp <= 3700]
            for market, values in histories.items()
        }

        self.assertIsNotNone(state)
        self.assertEqual(state.vector, market_data.build_weather_map_vector(truncated))

    def test_analog_search_never_uses_future_state_or_unavailable_outcome(self) -> None:
        target = [market_data.Candle(index, 100 + index, 100 + index, 100 + index,
                                     100 + index, None) for index in range(50)]
        current = market_data.WeatherMapState(40, (0.0,) * 26)
        states = [market_data.WeatherMapState(index, (index / 100,) * 26)
                  for index in range(10, 50)]

        result = market_data.find_analogs(current, states, target)

        self.assertIsNotNone(result)
        self.assertTrue(all(timestamp < current.timestamp for timestamp, _ in result.nearest))


if __name__ == "__main__":
    unittest.main()
