import json
import tempfile
import unittest
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts import fetch_market_data as market_data
from scripts import save_live_forecast


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
        self.assertGreaterEqual(prediction["trend_confidence"], 0)
        self.assertLessEqual(prediction["trend_confidence"], 1)
        self.assertLess(prediction["range_low"], prediction["current"])
        self.assertLess(prediction["current"], prediction["range_high"])
        self.assertEqual(prediction["weather"], "sunny")
        self.assertEqual(prediction["risk"], "calm")

    def test_last_data_date_uses_latest_completed_candle_local_date(self) -> None:
        ny_close = market_data.Candle(
            int(datetime(2026, 9, 21, 16, 0, tzinfo=ZoneInfo("America/New_York")).timestamp()),
            100.0, 101.0, 99.0, 100.5, None,
        )

        self.assertEqual(
            market_data.last_data_date("^DJI", candles()[:-1] + [ny_close]),
            "2026-09-21",
        )

    def test_next_session_date_skips_us_holiday_and_weekend(self) -> None:
        ny_close = market_data.Candle(
            int(datetime(2026, 9, 4, 16, 0, tzinfo=ZoneInfo("America/New_York")).timestamp()),
            100.0, 101.0, 99.0, 100.5, None,
        )

        self.assertEqual(
            market_data.next_session_date("^DJI", candles()[:-1] + [ny_close]),
            "2026-09-08",
        )

    def test_next_session_date_does_not_apply_nyse_holidays_to_fx(self) -> None:
        fx_close = market_data.Candle(
            int(datetime(2026, 9, 4, 17, 0, tzinfo=ZoneInfo("America/New_York")).timestamp()),
            100.0, 101.0, 99.0, 100.5, None,
        )

        self.assertEqual(
            market_data.next_session_date("JPY=X", candles()[:-1] + [fx_close]),
            "2026-09-07",
        )

    def test_preopen_usdjpy_target_advances_sunday_and_weekdays_across_dst(self) -> None:
        cases = [
            ("2026-01-04T20:00:00+00:00", "2026-01-02", "2026-01-05"),
            ("2026-01-05T20:00:00+00:00", "2026-01-02", "2026-01-06"),
            ("2026-07-05T20:00:00+00:00", "2026-07-03", "2026-07-06"),
            ("2026-07-06T20:00:00+00:00", "2026-07-03", "2026-07-07"),
            ("2026-07-07T20:00:00+00:00", "2026-07-06", "2026-07-08"),
            ("2026-07-08T20:00:00+00:00", "2026-07-07", "2026-07-09"),
            ("2026-07-09T20:00:00+00:00", "2026-07-08", "2026-07-10"),
        ]
        for generated, last_completed, expected in cases:
            with self.subTest(generated=generated):
                self.assertEqual(
                    market_data.next_usdjpy_session_after(
                        datetime.fromisoformat(generated), last_completed
                    ),
                    expected,
                )

    def test_delayed_preopen_usdjpy_run_never_targets_an_open_session(self) -> None:
        cases = [
            ("2026-01-05T21:59:59+00:00", "2026-01-02", "2026-01-06"),
            ("2026-01-05T22:00:00+00:00", "2026-01-02", "2026-01-07"),
            ("2026-07-06T20:59:59+00:00", "2026-07-03", "2026-07-07"),
            ("2026-07-06T21:00:00+00:00", "2026-07-03", "2026-07-08"),
        ]
        for generated, last_completed, expected in cases:
            with self.subTest(generated=generated):
                moment = datetime.fromisoformat(generated)
                target = market_data.next_usdjpy_session_after(moment, last_completed)
                self.assertEqual(target, expected)
                eastern = ZoneInfo("America/New_York")
                opening = datetime.combine(
                    date.fromisoformat(target) - timedelta(days=1),
                    time(17),
                    tzinfo=eastern,
                )
                self.assertLess(moment, opening)

    def test_preopen_override_changes_only_usdjpy_target_in_saved_forecast(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "forecast.json"
            path.write_text(json.dumps({"markets": [
                {"id": market_id} for market_id in market_data.MARKET_ORDER
            ]}), encoding="utf-8")
            predictions = {
                market_id: {
                    "last_data_date": "2026-07-03",
                    "next_session_date": "2026-07-06",
                }
                for market_id in market_data.MARKET_ORDER
            }
            generated = datetime(2026, 7, 6, 20, tzinfo=timezone.utc)
            market_data._write_forecast(
                path,
                predictions,
                advance_usdjpy_target=True,
                generated_at=generated,
            )
            saved = json.loads(path.read_text(encoding="utf-8"))
            snapshot_path, created = save_live_forecast.save_snapshot(
                path, Path(directory) / "snapshots"
            )
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))

        targets = {
            market["id"]: market["next_session_date"] for market in saved["markets"]
        }
        self.assertEqual(targets["usdjpy"], "2026-07-07")
        self.assertEqual(
            {targets[market] for market in ("nikkei", "dow", "gold")},
            {"2026-07-06"},
        )
        self.assertEqual(saved["generated_at"], "2026-07-06T20:00:00+00:00")
        self.assertTrue(created)
        snapshot_usdjpy = next(
            market for market in snapshot["forecast"]["markets"]
            if market["id"] == "usdjpy"
        )
        self.assertEqual(snapshot_usdjpy["next_session_date"], "2026-07-07")

    def test_next_session_date_does_not_apply_nyse_holidays_to_gold(self) -> None:
        gold_close = market_data.Candle(
            int(datetime(2026, 9, 4, 17, 0, tzinfo=ZoneInfo("America/New_York")).timestamp()),
            100.0, 101.0, 99.0, 100.5, None,
        )

        self.assertEqual(
            market_data.next_session_date("GC=F", candles()[:-1] + [gold_close]),
            "2026-09-07",
        )

    def test_next_session_date_gold_skips_full_christmas_closure(self) -> None:
        gold_close = market_data.Candle(
            int(datetime(2026, 12, 24, 17, 0, tzinfo=ZoneInfo("America/New_York")).timestamp()),
            100.0, 101.0, 99.0, 100.5, None,
        )

        self.assertEqual(
            market_data.next_session_date("GC=F", candles()[:-1] + [gold_close]),
            "2026-12-28",
        )

    def test_next_session_date_skips_japan_holiday_stretch(self) -> None:
        tokyo_close = market_data.Candle(
            int(datetime(2026, 9, 18, 15, 30, tzinfo=ZoneInfo("Asia/Tokyo")).timestamp()),
            100.0, 101.0, 99.0, 100.5, None,
        )

        self.assertEqual(
            market_data.next_session_date("^N225", candles()[:-1] + [tokyo_close]),
            "2026-09-24",
        )

    def test_next_session_date_uses_shifted_2021_japan_holidays(self) -> None:
        tokyo_close = market_data.Candle(
            int(datetime(2021, 7, 21, 15, 30, tzinfo=ZoneInfo("Asia/Tokyo")).timestamp()),
            100.0, 101.0, 99.0, 100.5, None,
        )

        self.assertEqual(
            market_data.next_session_date("^N225", candles()[:-1] + [tokyo_close]),
            "2021-07-26",
        )

    def test_next_session_date_rejects_unsupported_japan_calendar_years(self) -> None:
        tokyo_close = market_data.Candle(
            int(datetime(2015, 12, 30, 15, 0, tzinfo=ZoneInfo("Asia/Tokyo")).timestamp()),
            100.0, 101.0, 99.0, 100.5, None,
        )

        with self.assertRaisesRegex(ValueError, "Japanese next-session calendar supports years"):
            market_data.next_session_date("^N225", candles()[:-1] + [tokyo_close])

    def test_weather_and_risk_thresholds(self) -> None:
        self.assertEqual([market_data.weather_for_probability(value) for value in (0.7, 0.6, 0.5, 0.4)],
                         ["sunny", "partly_cloudy", "cloudy", "rainy"])
        self.assertEqual([market_data.risk_for_volatility(value) for value in (0.005, 0.01, 0.02, 0.03)],
                         ["calm", "normal", "caution", "storm"])


class WeatherMapTest(unittest.TestCase):
    def test_vector_contains_twenty_market_and_six_pair_features(self) -> None:
        histories = {market: candles(growth=0.001 * (index + 1))
                     for index, market in enumerate(market_data.MARKET_ORDER)}

        vector = market_data.build_weather_map_vector(histories)

        self.assertEqual(len(vector), 26)
        self.assertEqual(len(vector), len(market_data.WEATHER_MAP_FEATURE_NAMES))
        # The first relative feature is Nikkei n5 minus Dow n5.
        self.assertAlmostEqual(vector[20], vector[1] - vector[6])
        self.assertEqual(len(market_data.weather_map_feature_names("nikkei")), 30)
        self.assertEqual(
            market_data.weather_map_feature_names("nikkei")[-4:],
            (
                "nikkei_hours_since_close",
                "dow_return_since_nikkei_close",
                "usdjpy_return_since_nikkei_close",
                "gold_return_since_nikkei_close",
            ),
        )

    def test_identical_state_is_nearer_and_search_is_capped_at_k(self) -> None:
        target = candles(count=70)
        query = market_data.WeatherMapState(target[-1].timestamp, (0.0,) * 26)
        states = [
            market_data.WeatherMapState(target[index].timestamp, (index / 100,) * 26)
            for index in range(21, 69)
        ]

        result = market_data.find_analogs(query, states, target)

        self.assertIsNotNone(result)
        self.assertEqual(result.count, market_data.ANALOG_K)
        self.assertGreaterEqual(result.probability, 0)
        self.assertLessEqual(result.probability, 1)
        distances = market_data._standardized_distances(
            query.vector, [(states[0], 0.01), (market_data.WeatherMapState(1, (2.0,) * 26), 0.01)]
        )
        self.assertLess(distances[0][0], distances[1][0])

    def test_too_few_analogs_falls_back_to_trend(self) -> None:
        snapshots = {market: market_data.MarketSnapshot(candles(count=30), 101.0)
                     for market in market_data.MARKET_ORDER}

        predictions, _ = market_data.build_cross_asset_predictions(snapshots)

        for prediction in predictions.values():
            self.assertEqual(prediction["analog_count"], 0)
            self.assertIsNone(prediction["analog_probability"])
            self.assertEqual(prediction["up_probability"], prediction["trend_probability"])
            self.assertEqual(prediction["confidence"], prediction["trend_confidence"])

    def test_candidate_a_rewards_agreement_and_analog_support(self) -> None:
        def analog(probability: float, count: int = market_data.ANALOG_K):
            return market_data.AnalogResult(
                probability, count, 1.0, 0.0, (), distance_quality=0.8
            )

        close = market_data.candidate_a_confidence(0.68, 0.7, analog(0.72))
        disagreement = market_data.candidate_a_confidence(0.68, 0.7, analog(0.32))
        sparse = market_data.candidate_a_confidence(0.68, 0.7, analog(0.72, 20))

        self.assertGreaterEqual(close, disagreement)
        self.assertGreater(close, sparse)
        self.assertGreaterEqual(disagreement, 0.0)
        self.assertLessEqual(close, 1.0)

    def test_candidate_a_without_analog_is_trend_confidence(self) -> None:
        self.assertEqual(market_data.candidate_a_confidence(0.7, 0.63, None), 0.63)

    def test_continuous_agreement_has_no_neutral_threshold_jump(self) -> None:
        same_side = market_data.continuous_agreement(0.5001, 0.5001)
        opposite_sides = market_data.continuous_agreement(0.5001, 0.4999)
        material_opposition = market_data.continuous_agreement(0.68, 0.32)

        self.assertAlmostEqual(same_side, opposite_sides, places=3)
        self.assertGreater(opposite_sides, material_opposition)

    def test_forecast_support_reflects_each_material_without_changing_forecast(self) -> None:
        def analog(
            probability: float = 0.72,
            distance_quality: float = 0.8,
            effective_sample_size: float = 27.0,
        ) -> market_data.AnalogResult:
            return market_data.AnalogResult(
                probability, market_data.ANALOG_K, 1.0, 0.0, (),
                distance_quality, effective_sample_size,
            )

        baseline = market_data.calculate_forecast_support(0.68, 0.8, analog())
        self.assertGreater(baseline, market_data.calculate_forecast_support(
            0.68, 0.8, analog(probability=0.32)
        ))
        self.assertGreater(baseline, market_data.calculate_forecast_support(
            0.68, 0.8, analog(distance_quality=0.2)
        ))
        self.assertGreater(baseline, market_data.calculate_forecast_support(
            0.68, 0.8, analog(effective_sample_size=6.0)
        ))
        self.assertGreater(baseline, market_data.calculate_forecast_support(
            0.68, 0.2, analog()
        ))
        self.assertGreaterEqual(baseline, 0.0)
        self.assertLessEqual(baseline, 1.0)

    def test_forecast_support_is_continuous_at_neutral_boundary(self) -> None:
        above = market_data.AnalogResult(0.5001, 30, 1.0, 0.0, (), 0.8, 25)
        below = market_data.AnalogResult(0.4999, 30, 1.0, 0.0, (), 0.8, 25)

        same_side = market_data.calculate_forecast_support(0.5001, 0.8, above)
        crossed = market_data.calculate_forecast_support(0.5001, 0.8, below)

        self.assertAlmostEqual(same_side, crossed, places=3)

    def test_forecast_support_without_analog_uses_only_trend_component(self) -> None:
        self.assertAlmostEqual(
            market_data.calculate_forecast_support(0.7, 0.8, None), 0.28
        )


if __name__ == "__main__":
    unittest.main()
