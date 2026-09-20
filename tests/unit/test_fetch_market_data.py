import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import fetch_market_data


class FetchMarketDataTest(unittest.TestCase):
    def test_updates_only_current_values_and_generated_at(self) -> None:
        original = {
            "generated_at": "2026-01-01T00:00:00+00:00",
            "markets": [
                {
                    "id": market_id,
                    "current": 1.0,
                    "up_probability": 0.5,
                    "range_low": 0.5,
                    "range_high": 1.5,
                    "confidence": 0.7,
                    "weather": "cloudy",
                    "risk": "normal",
                }
                for market_id in fetch_market_data.SYMBOLS
            ],
        }
        prices = {"nikkei": 42001.0, "dow": 46002.0, "usdjpy": 147.03, "gold": 3684.0}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "forecast.json"
            path.write_text(json.dumps(original), encoding="utf-8")
            with patch.object(
                fetch_market_data,
                "fetch_price",
                side_effect=lambda symbol: prices[next(key for key, value in fetch_market_data.SYMBOLS.items() if value == symbol)],
            ):
                result = fetch_market_data.update_forecast(path)

            updated = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(result, prices)
        self.assertNotEqual(updated["generated_at"], original["generated_at"])
        for before, after in zip(original["markets"], updated["markets"]):
            self.assertEqual(after["current"], prices[after["id"]])
            self.assertEqual(
                {key: value for key, value in after.items() if key != "current"},
                {key: value for key, value in before.items() if key != "current"},
            )

    def test_rejects_incomplete_response(self) -> None:
        response = unittest.mock.MagicMock()
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        with patch.object(fetch_market_data, "urlopen", return_value=response), patch.object(
            fetch_market_data.json, "load", return_value={"chart": {"result": []}}
        ):
            with self.assertRaisesRegex(ValueError, "No current price"):
                fetch_market_data.fetch_price("^N225")


if __name__ == "__main__":
    unittest.main()
