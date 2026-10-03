import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts import fetch_market_data as market_data
from scripts import score_live_forecast


class ProspectiveScoringTest(unittest.TestCase):
    @staticmethod
    def _candle(year: int, month: int, day: int, close_hour: int, close_minute: int, tz_name: str, close: float) -> market_data.Candle:
        return market_data.Candle(
            int(datetime(year, month, day, close_hour, close_minute, tzinfo=ZoneInfo(tz_name)).timestamp()),
            close,
            close,
            close,
            close,
            None,
        )

    def test_scores_completed_market_and_waits_unsettled_market(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prospective_dir = root / "reports" / "live-forecast"
            prospective_dir.mkdir(parents=True)
            history_path = root / "reports" / "live-forecast-history.json"
            history_path.parent.mkdir(parents=True, exist_ok=True)
            history_path.write_text("[]\n", encoding="utf-8")
            prospective = {
                "source_generated_at": "2026-09-21T08:07:02+00:00",
                "forecast": {
                    "markets": [
                        {
                            "id": "dow",
                            "up_probability": 0.11,
                            "trend_probability": 0.21,
                            "analog_probability": 0.31,
                            "range_low": 90,
                            "range_high": 105,
                        },
                        {
                            "id": "nikkei",
                            "up_probability": 0.8,
                            "trend_probability": 0.7,
                            "analog_probability": 0.6,
                            "range_low": 100,
                            "range_high": 110,
                        },
                    ]
                },
            }
            (prospective_dir / "2026-09-21.json").write_text(
                json.dumps(prospective), encoding="utf-8"
            )
            histories = {
                "dow": [
                    self._candle(2026, 9, 18, 16, 0, "America/New_York", 100),
                    self._candle(2026, 9, 21, 16, 0, "America/New_York", 95),
                    self._candle(2026, 9, 22, 16, 0, "America/New_York", 96),
                ],
                "nikkei": [
                    self._candle(2026, 9, 18, 15, 30, "Asia/Tokyo", 100),
                ],
                "usdjpy": [
                    self._candle(2026, 9, 18, 17, 0, "America/New_York", 150),
                    self._candle(2026, 9, 21, 17, 0, "America/New_York", 151),
                ],
                "gold": [
                    self._candle(2026, 9, 18, 17, 0, "America/New_York", 4300),
                    self._candle(2026, 9, 21, 17, 0, "America/New_York", 4310),
                ],
            }

            summary = score_live_forecast.score_prospective_forecasts(
                prospective_dir=prospective_dir,
                history_path=history_path,
                histories=histories,
            )
            records = json.loads(history_path.read_text(encoding="utf-8"))

        self.assertEqual(summary["processed"], 2)
        self.assertEqual(summary["added"], 1)
        self.assertEqual(summary["waiting"], 1)
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["market"], "dow")
        self.assertEqual(record["target_session_date"], "2026-09-21")
        self.assertEqual(record["trend_probability"], 0.21)
        self.assertEqual(record["analog_probability"], 0.31)
        self.assertEqual(record["ensemble_probability"], 0.11)
        self.assertEqual(record["actual_direction"], "down")
        self.assertTrue(record["ensemble_correct"])
        self.assertAlmostEqual(record["ensemble_brier_contribution"], 0.11**2)
        self.assertAlmostEqual(record["trend_brier_contribution"], 0.21**2)
        self.assertAlmostEqual(record["analog_brier_contribution"], 0.31**2)
        self.assertTrue(record["actual_in_predicted_range"])

    def test_does_not_add_duplicate_record_for_same_forecast_market_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prospective_dir = root / "reports" / "live-forecast"
            prospective_dir.mkdir(parents=True)
            history_path = root / "reports" / "live-forecast-history.json"
            history_path.parent.mkdir(parents=True, exist_ok=True)
            history_path.write_text("[]\n", encoding="utf-8")
            (prospective_dir / "2026-09-21.json").write_text(
                json.dumps(
                    {
                        "source_generated_at": "2026-09-21T08:07:02+00:00",
                        "forecast": {
                            "markets": [{
                                "id": "dow",
                                "up_probability": 0.6,
                                "trend_probability": 0.6,
                                "analog_probability": 0.6,
                                "range_low": 90,
                                "range_high": 120,
                                "next_session_date": "2026-09-21",
                            }]
                        },
                    }
                ),
                encoding="utf-8",
            )
            histories = {
                "dow": [
                    self._candle(2026, 9, 18, 16, 0, "America/New_York", 100),
                    self._candle(2026, 9, 21, 16, 0, "America/New_York", 101),
                ],
                "nikkei": [self._candle(2026, 9, 18, 15, 30, "Asia/Tokyo", 100)],
                "usdjpy": [self._candle(2026, 9, 18, 17, 0, "America/New_York", 150)],
                "gold": [self._candle(2026, 9, 18, 17, 0, "America/New_York", 4300)],
            }

            first = score_live_forecast.score_prospective_forecasts(
                prospective_dir=prospective_dir,
                history_path=history_path,
                histories=histories,
            )
            second = score_live_forecast.score_prospective_forecasts(
                prospective_dir=prospective_dir,
                history_path=history_path,
                histories=histories,
            )
            records = json.loads(history_path.read_text(encoding="utf-8"))

        self.assertEqual(first["added"], 1)
        self.assertEqual(second["added"], 0)
        self.assertEqual(len(records), 1)

    def test_does_not_score_stale_target_as_retrospective_forecast(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prospective_dir = root / "reports" / "live-forecast"
            prospective_dir.mkdir(parents=True)
            history_path = root / "reports" / "live-forecast-history.json"
            history_path.parent.mkdir(parents=True, exist_ok=True)
            history_path.write_text("[]\n", encoding="utf-8")
            (prospective_dir / "stale.json").write_text(
                json.dumps({
                    "source_generated_at": "2026-10-03T01:15:54+00:00",
                    "forecast": {"markets": [{
                        "id": "nikkei",
                        "next_session_date": "2026-10-02",
                        "up_probability": 0.99,
                        "trend_probability": 0.99,
                        "analog_probability": 0.99,
                    }]},
                }),
                encoding="utf-8",
            )
            histories = {"nikkei": [
                self._candle(2026, 10, 1, 15, 30, "Asia/Tokyo", 100),
                self._candle(2026, 10, 2, 15, 30, "Asia/Tokyo", 110),
            ]}

            summary = score_live_forecast.score_prospective_forecasts(
                prospective_dir, history_path, histories
            )

            self.assertEqual(summary["processed"], 1)
            self.assertEqual(summary["added"], 0)
            self.assertEqual(json.loads(history_path.read_text(encoding="utf-8")), [])

    def test_multiple_days_and_market_specific_sessions_are_scored_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prospective_dir = root / "reports" / "live-forecast"
            prospective_dir.mkdir(parents=True)
            history_path = root / "reports" / "history.json"
            history_path.parent.mkdir(parents=True, exist_ok=True)
            history_path.write_text("[]\n", encoding="utf-8")

            targets = {
                "nikkei": ("2026-09-24", 0.8),  # three-day holiday closure
                "dow": ("2026-09-21", 0.7),
                "usdjpy": ("2026-09-22", 0.4),
                "gold": ("2026-09-23", 0.3),
            }
            for day, generated_at in enumerate(
                ("2026-09-20T12:00:00+00:00", "2026-09-21T12:00:00+00:00")
            ):
                markets = [
                    {
                        "id": market_id,
                        "next_session_date": target_date,
                        "up_probability": probability,
                    }
                    for market_id, (target_date, probability) in targets.items()
                ]
                (prospective_dir / f"snapshot-{day}.json").write_text(
                    json.dumps(
                        {
                            "source_generated_at": generated_at,
                            "forecast": {"markets": markets},
                        }
                    ),
                    encoding="utf-8",
                )

            histories = {
                "nikkei": [
                    self._candle(2026, 9, 18, 15, 30, "Asia/Tokyo", 100),
                    self._candle(2026, 9, 24, 15, 30, "Asia/Tokyo", 101),
                ],
                "dow": [
                    self._candle(2026, 9, 18, 16, 0, "America/New_York", 100),
                    self._candle(2026, 9, 21, 16, 0, "America/New_York", 99),
                ],
                "usdjpy": [
                    self._candle(2026, 9, 21, 17, 0, "America/New_York", 100),
                    self._candle(2026, 9, 22, 17, 0, "America/New_York", 100),
                ],
                "gold": [self._candle(2026, 9, 22, 17, 0, "America/New_York", 100)],
            }

            first = score_live_forecast.score_prospective_forecasts(
                prospective_dir, history_path, histories
            )
            histories["gold"].append(
                self._candle(2026, 9, 23, 17, 0, "America/New_York", 102)
            )
            second = score_live_forecast.score_prospective_forecasts(
                prospective_dir, history_path, histories
            )
            third = score_live_forecast.score_prospective_forecasts(
                prospective_dir, history_path, histories
            )
            records = json.loads(history_path.read_text(encoding="utf-8"))

        self.assertEqual(first["added"], 6)
        self.assertEqual(first["waiting"], 2)
        self.assertEqual(second["added"], 2)
        self.assertEqual(third["added"], 0)
        self.assertEqual(len(records), 8)
        flat = next(record for record in records if record["market"] == "usdjpy")
        self.assertEqual(flat["actual_direction"], "flat")
        self.assertIsNone(flat["ensemble_correct"])
        self.assertIsNone(flat["ensemble_brier_contribution"])


if __name__ == "__main__":
    unittest.main()
