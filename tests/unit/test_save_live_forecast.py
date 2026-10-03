import json
import tempfile
import unittest
from pathlib import Path

from scripts.save_live_forecast import save_snapshot


class SaveLiveForecastTest(unittest.TestCase):
    def test_creates_snapshot_and_same_forecast_is_noop(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "forecast.json"
            target = root / "snapshots"
            forecast = {
                "generated_at": "2026-10-03T01:15:54+00:00",
                "markets": [{"id": "dow", "up_probability": 0.6}],
            }
            source.write_text(json.dumps(forecast), encoding="utf-8")

            path, created = save_snapshot(source, target)
            same_path, created_again = save_snapshot(source, target)

            self.assertTrue(created)
            self.assertFalse(created_again)
            self.assertEqual(path, same_path)
            self.assertEqual(path.name, "2026-10-03T01-15-54Z.json")
            self.assertEqual(json.loads(path.read_text())["forecast"], forecast)
            self.assertEqual(len(list(target.glob("*.json"))), 1)

    def test_rejects_different_payload_for_same_generated_at(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "forecast.json"
            target = root / "snapshots"
            source.write_text(
                json.dumps({"generated_at": "2026-10-03T01:15:54Z", "markets": []}),
                encoding="utf-8",
            )
            save_snapshot(source, target)
            source.write_text(
                json.dumps({"generated_at": "2026-10-03T01:15:54Z", "markets": [{"id": "gold"}]}),
                encoding="utf-8",
            )

            with self.assertRaises(FileExistsError):
                save_snapshot(source, target)


if __name__ == "__main__":
    unittest.main()
