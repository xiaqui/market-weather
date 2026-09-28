import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from scripts import fetch_market_data as market_data


class BacktestRegressionTest(unittest.TestCase):
    @staticmethod
    def market_rows(last_index=29, growth=0.0, missing=()):
        rows = []
        close = 100.0
        for index in range(last_index + 1):
            if index in missing:
                continue
            close *= 1 + growth
            timestamp = 1_700_000_000 + index * 86_400
            rows.append(market_data.Candle(timestamp, close, close, close, close, None))
        return rows

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

    def test_last_data_date_does_not_use_in_progress_daily_candle(self) -> None:
        ny = ZoneInfo("America/New_York")
        session_start = int(datetime(2026, 9, 22, 9, 30, tzinfo=ny).timestamp())
        timestamps = [
            int(datetime(2026, 9, day, 9, 30, tzinfo=ny).timestamp())
            for day in range(1, 22)
        ] + [session_start]
        payload = {
            "chart": {"result": [{
                "meta": {"currentTradingPeriod": {"regular": {
                    "start": session_start,
                    "end": session_start + 6 * 3600 + 30 * 60,
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
            payload, "^DJI", now_timestamp=session_start + 100
        )

        self.assertEqual(market_data.last_data_date("^DJI", parsed), "2026-09-21")

    def test_saturday_jst_uses_completed_friday_nikkei_and_gold_rows(self) -> None:
        saturday_morning = datetime(
            2026, 9, 26, 7, 30, tzinfo=ZoneInfo("Asia/Tokyo")
        ).timestamp()

        def payload(timestamps):
            count = len(timestamps)
            return {"chart": {"result": [{
                # Deliberately point metadata at a later session. Weekend
                # completion must be decided from each candle's own close.
                "meta": {"currentTradingPeriod": {"regular": {
                    "start": int(saturday_morning) + 100_000,
                    "end": int(saturday_morning) + 200_000,
                }}},
                "timestamp": timestamps,
                "indicators": {"quote": [{
                    "open": [100.0] * count,
                    "high": [101.0] * count,
                    "low": [99.0] * count,
                    "close": [100.0] * count,
                    "volume": [1000] * count,
                }]},
            }]}}

        cases = {
            "^N225": datetime(2026, 9, 25, tzinfo=ZoneInfo("UTC")),
            "^DJI": datetime(2026, 9, 25, 13, 30, tzinfo=ZoneInfo("UTC")),
            # Yahoo's London feed labels the Friday FX row at 23:00 UTC
            # Thursday while British daylight saving is active.
            "JPY=X": datetime(2026, 9, 24, 23, 0, tzinfo=ZoneInfo("UTC")),
            "GC=F": datetime(2026, 9, 25, 4, 0, tzinfo=ZoneInfo("UTC")),
        }
        for symbol, friday_label in cases.items():
            with self.subTest(symbol=symbol):
                timestamps = [int(friday_label.timestamp()) - day * 86_400
                              for day in range(20, -1, -1)]
                parsed = market_data.parse_history(
                    payload(timestamps), symbol, now_timestamp=saturday_morning
                )

                self.assertEqual(market_data.last_data_date(symbol, parsed), "2026-09-25")
                self.assertEqual(market_data.next_session_date(symbol, parsed), "2026-09-28")

    def test_market_close_cutoff_still_excludes_a_forming_row(self) -> None:
        now = datetime(2026, 9, 28, 12, 0, tzinfo=ZoneInfo("Asia/Tokyo")).timestamp()
        friday = int(datetime(2026, 9, 25, tzinfo=ZoneInfo("UTC")).timestamp())
        monday = int(datetime(2026, 9, 28, tzinfo=ZoneInfo("UTC")).timestamp())
        timestamps = [friday - day * 86_400 for day in range(20, -1, -1)] + [monday]
        count = len(timestamps)
        payload = {"chart": {"result": [{
            "timestamp": timestamps,
            "indicators": {"quote": [{
                "open": [100.0] * count, "high": [101.0] * count,
                "low": [99.0] * count, "close": [100.0] * count,
                "volume": [1000] * count,
            }]},
        }]}}

        parsed = market_data.parse_history(payload, "^N225", now_timestamp=now)

        self.assertEqual(market_data.last_data_date("^N225", parsed), "2026-09-25")

    def test_next_session_date_handles_2026_09_21_holiday_gap(self) -> None:
        nikkei_close = market_data.Candle(
            int(datetime(2026, 9, 18, 15, 30, tzinfo=ZoneInfo("Asia/Tokyo")).timestamp()),
            100.0, 101.0, 99.0, 100.5, None,
        )
        dow_close = market_data.Candle(
            int(datetime(2026, 9, 21, 16, 0, tzinfo=ZoneInfo("America/New_York")).timestamp()),
            100.0, 101.0, 99.0, 100.5, None,
        )

        self.assertEqual(
            market_data.next_session_date("^N225", [nikkei_close]),
            "2026-09-24",
        )
        self.assertEqual(
            market_data.next_session_date("^DJI", [dow_close]),
            "2026-09-22",
        )

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

        state = market_data.weather_map_at(histories, 3700, "nikkei")
        truncated = {
            market: [row for row in values if row.timestamp <= 3700]
            for market, values in histories.items()
        }

        self.assertIsNotNone(state)
        self.assertEqual(state.vector[:26], market_data.build_weather_map_vector(truncated))

    def test_analog_search_never_uses_future_state_or_unavailable_outcome(self) -> None:
        target = [market_data.Candle(index, 100 + index, 100 + index, 100 + index,
                                     100 + index, None) for index in range(50)]
        current = market_data.WeatherMapState(40, (0.0,) * 26)
        states = [market_data.WeatherMapState(index, (index / 100,) * 26)
                  for index in range(10, 50)]

        result = market_data.find_analogs(current, states, target)

        self.assertIsNotNone(result)
        self.assertTrue(all(timestamp < current.timestamp for timestamp, _ in result.nearest))

    def test_each_historical_session_uses_its_own_normal_or_early_close(self) -> None:
        ny = ZoneInfo("America/New_York")
        normal_label = int(datetime(2025, 11, 26, 9, 30, tzinfo=ny).timestamp())
        early_label = int(datetime(2025, 11, 28, 9, 30, tzinfo=ny).timestamp())

        normal = datetime.fromtimestamp(
            market_data.session_close_timestamp("^DJI", normal_label), ny
        )
        early = datetime.fromtimestamp(
            market_data.session_close_timestamp("^DJI", early_label), ny
        )

        self.assertEqual((normal.hour, normal.minute), (16, 0))
        self.assertEqual((early.hour, early.minute), (13, 0))

    def test_current_session_end_is_not_reused_for_historical_rows(self) -> None:
        ny = ZoneInfo("America/New_York")
        labels = [
            int(datetime(2025, 10, day, 9, 30, tzinfo=ny).timestamp())
            for day in range(1, 22)
        ]
        today_start = int(datetime(2025, 11, 28, 9, 30, tzinfo=ny).timestamp())
        today_end = int(datetime(2025, 11, 28, 13, 0, tzinfo=ny).timestamp())
        payload = {"chart": {"result": [{
            "meta": {
                "exchangeTimezoneName": "America/New_York",
                "currentTradingPeriod": {"regular": {
                    "start": today_start, "end": today_end,
                }},
            },
            "timestamp": labels,
            "indicators": {"quote": [{
                "open": [100.0] * 21, "high": [101.0] * 21,
                "low": [99.0] * 21, "close": [100.0] * 21,
                "volume": [1000] * 21,
            }]},
        }]}}

        parsed = market_data.parse_history(payload, "^DJI", now_timestamp=today_end + 1)

        closes = [datetime.fromtimestamp(row.timestamp, ny).hour for row in parsed]
        self.assertEqual(closes, [16] * 21)

    def test_target_snapshot_excludes_us_close_after_tokyo_clock(self) -> None:
        histories = {
            market: self.market_rows() for market in market_data.MARKET_ORDER
        }
        tokyo_clock = histories["nikkei"][-1].timestamp
        future_us = market_data.Candle(
            tokyo_clock + 8 * 3600, 500, 500, 500, 500, None
        )
        histories["dow"].append(future_us)

        state = market_data.weather_map_at(histories, tokyo_clock, "nikkei")
        without_future = dict(histories)
        without_future["dow"] = histories["dow"][:-1]

        self.assertEqual(
            state.vector,
            market_data.weather_map_at(without_future, tokyo_clock, "nikkei").vector,
        )

    def test_holiday_staleness_and_accumulated_external_moves(self) -> None:
        histories = {
            market: self.market_rows() for market in market_data.MARKET_ORDER
        }
        # Japan is closed for two global daily clocks while the other markets trade.
        histories["nikkei"] = self.market_rows(last_index=27)
        state = market_data.weather_map_at(
            histories, histories["dow"][-1].timestamp, "nikkei"
        )

        self.assertAlmostEqual(state.vector[26], 48.0)
        self.assertEqual(state.target_close_timestamp, histories["nikkei"][-1].timestamp)
        self.assertTrue(all(abs(value) < 1e-12 for value in state.vector[27:]))

        moving = dict(histories)
        moving["dow"] = self.market_rows(growth=0.01)
        moved_state = market_data.weather_map_at(
            moving, moving["dow"][-1].timestamp, "nikkei"
        )
        expected = moving["dow"][-1].close / moving["dow"][-3].close - 1
        self.assertAlmostEqual(moved_state.vector[27], expected)
        self.assertGreater(moved_state.vector[27], 0)

    def test_asof_join_handles_each_market_holiday_and_single_market_updates(self) -> None:
        scenarios = {
            "japan_closed": {"nikkei": (29,)},
            "us_closed": {"dow": (29,)},
            "forex_only": {"nikkei": (29,), "dow": (29,), "gold": (29,)},
            "gold_only": {"nikkei": (29,), "dow": (29,), "usdjpy": (29,)},
        }
        for name, missing_by_market in scenarios.items():
            with self.subTest(name=name):
                histories = {
                    market: self.market_rows(missing=missing_by_market.get(market, ()))
                    for market in market_data.MARKET_ORDER
                }
                clock = max(rows[-1].timestamp for rows in histories.values())
                state = market_data.weather_map_at(histories, clock, "nikkei")
                self.assertIsNotNone(state)
                for market, rows in histories.items():
                    self.assertLessEqual(
                        market_data._asof_candle(rows, clock).timestamp, clock,
                        market,
                    )

    def test_live_and_backtest_use_the_same_snapshot_clock_function(self) -> None:
        histories = {
            market: self.market_rows() for market in market_data.MARKET_ORDER
        }
        target = histories["nikkei"]
        expected = market_data.snapshot_clock(
            histories, "nikkei", target[-1].timestamp
        )
        historical = market_data._historical_states(histories, "nikkei")

        self.assertEqual(historical[-1].timestamp, expected)
        self.assertEqual(
            market_data.snapshot_clock(histories, "nikkei"),
            max(rows[-1].timestamp for rows in histories.values()),
        )

    def test_expanding_historical_up_rate_excludes_predicted_outcome(self) -> None:
        target = self.market_rows(last_index=24, growth=0.01)
        histories = {market: list(target) for market in market_data.MARKET_ORDER}
        current = market_data.WeatherMapState(target[-1].timestamp, (0.0,) * 30)

        with (
            patch.object(market_data, "_historical_states", return_value=[]),
            patch.object(market_data, "snapshot_clock", return_value=target[-1].timestamp),
            patch.object(market_data, "weather_map_at", return_value=current),
            patch.object(market_data, "find_analogs", return_value=None),
            patch.object(market_data, "build_prediction", return_value={"trend_probability": 0.5}),
        ):
            rising = market_data.walk_forward_records(histories, "nikkei", sessions=1)
            histories["nikkei"][-1] = market_data.Candle(
                target[-1].timestamp, 1.0, 1.0, 1.0, 1.0, None
            )
            falling = market_data.walk_forward_records(histories, "nikkei", sessions=1)

        self.assertTrue(rising[0].actual_up)
        self.assertFalse(falling[0].actual_up)
        self.assertEqual(rising[0].historical_up_probability, 1.0)
        self.assertEqual(
            rising[0].historical_up_probability,
            falling[0].historical_up_probability,
        )


if __name__ == "__main__":
    unittest.main()
