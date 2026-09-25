import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from scripts import fetch_market_data as market_data


def history(offset: float) -> list[market_data.Candle]:
    return [
        market_data.Candle(index, offset + index, offset + index + 1, offset + index - 1, offset + index, 100)
        for index in range(80)
    ]


class ForecastGenerationTest(unittest.TestCase):
    def test_generates_every_forecast_field(self) -> None:
        original = {"generated_at": "old", "markets": [
            {"id": market_id, "name": market_id, "current": 1} for market_id in market_data.SYMBOLS
        ]}
        expected_dates = {
            "nikkei": "2026-09-18",
            "dow": "2026-09-21",
            "usdjpy": "2026-09-21",
            "gold": "2026-09-21",
        }
        expected_next_sessions = {
            "nikkei": "2026-09-24",
            "dow": "2026-09-22",
            "usdjpy": "2026-09-22",
            "gold": "2026-09-22",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "forecast.json"
            path.write_text(json.dumps(original), encoding="utf-8")
            snapshots = [
                market_data.MarketSnapshot(
                    history(100),
                    200,
                ),
                market_data.MarketSnapshot(
                    history(200)[:-1] + [market_data.Candle(
                        int(datetime(2026, 9, 21, 16, 0, tzinfo=ZoneInfo("America/New_York")).timestamp()),
                        279, 280, 278, 279, 100,
                    )],
                    400,
                ),
                market_data.MarketSnapshot(
                    history(300)[:-1] + [market_data.Candle(
                        int(datetime(2026, 9, 21, 17, 0, tzinfo=ZoneInfo("America/New_York")).timestamp()),
                        379, 380, 378, 379, 100,
                    )],
                    600,
                ),
                market_data.MarketSnapshot(
                    history(400)[:-1] + [market_data.Candle(
                        int(datetime(2026, 9, 21, 17, 0, tzinfo=ZoneInfo("America/New_York")).timestamp()),
                        479, 480, 478, 479, 100,
                    )],
                    800,
                ),
            ]
            snapshots[0].candles[-1] = market_data.Candle(
                int(datetime(2026, 9, 18, 15, 30, tzinfo=ZoneInfo("Asia/Tokyo")).timestamp()),
                179, 180, 178, 179, 100,
            )
            with patch.object(market_data, "fetch_market", side_effect=snapshots):
                predictions = market_data.update_forecast(path)
            result = json.loads(path.read_text(encoding="utf-8"))

        self.assertNotEqual(result["generated_at"], "old")
        self.assertEqual(set(predictions), set(market_data.SYMBOLS))
        expected_fields = {
            "current", "trend_probability", "analog_probability", "analog_count",
            "analog_mean_distance", "analog_mean_next_return", "up_probability",
            "range_low", "range_high", "trend_confidence", "confidence", "weather", "risk",
            "last_data_date", "next_session_date",
            "forecast_support", "analog_effective_sample_size",
        }
        for item in result["markets"]:
            self.assertTrue(expected_fields <= item.keys())
            self.assertGreaterEqual(item["up_probability"], 0)
            self.assertLessEqual(item["up_probability"], 1)
            self.assertGreaterEqual(item["forecast_support"], 0)
            self.assertLessEqual(item["forecast_support"], 1)
            self.assertEqual(item["last_data_date"], expected_dates[item["id"]])
            self.assertEqual(
                item["next_session_date"], expected_next_sessions[item["id"]]
            )

    def test_does_not_modify_file_when_any_fetch_fails(self) -> None:
        original = json.dumps({"generated_at": "old", "markets": []})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "forecast.json"
            path.write_text(original, encoding="utf-8")
            with patch.object(market_data, "fetch_market", side_effect=RuntimeError("network")):
                with self.assertRaisesRegex(RuntimeError, "network"):
                    market_data.update_forecast(path)
            self.assertEqual(path.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
