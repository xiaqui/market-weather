import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "forecast.json"
            path.write_text(json.dumps(original), encoding="utf-8")
            snapshots = [
                market_data.MarketSnapshot(history(100 * (i + 1)), 200 * (i + 1))
                for i in range(4)
            ]
            with patch.object(market_data, "fetch_market", side_effect=snapshots):
                predictions = market_data.update_forecast(path)
            result = json.loads(path.read_text(encoding="utf-8"))

        self.assertNotEqual(result["generated_at"], "old")
        self.assertEqual(set(predictions), set(market_data.SYMBOLS))
        expected_fields = {
            "current", "trend_probability", "analog_probability", "analog_count",
            "analog_mean_distance", "analog_mean_next_return", "up_probability",
            "range_low", "range_high", "confidence", "weather", "risk",
        }
        for item in result["markets"]:
            self.assertTrue(expected_fields <= item.keys())
            self.assertGreaterEqual(item["up_probability"], 0)
            self.assertLessEqual(item["up_probability"], 1)

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
