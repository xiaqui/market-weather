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
                "markets": [{
                    "id": "dow",
                    "next_session_date": "2026-10-05",
                    "up_probability": 0.6,
                }],
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

    def test_run_38014689871_skips_stale_gold_and_saves_valid_markets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "forecast.json"
            target = root / "snapshots"
            source.write_text(
                json.dumps({
                    "generated_at": "2026-10-10T01:15:54+00:00",
                    "markets": [
                        {"id": "nikkei", "next_session_date": "2026-10-13"},
                        {"id": "dow", "next_session_date": "2026-10-12"},
                        {"id": "usdjpy", "next_session_date": "2026-10-12"},
                        {"id": "gold", "next_session_date": "2026-10-09"},
                    ],
                }),
                encoding="utf-8",
            )

            with self.assertLogs("scripts.save_live_forecast", level="WARNING") as logs:
                path, created = save_snapshot(source, target)

            self.assertTrue(created)
            self.assertIsNotNone(path)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(
                [market["id"] for market in saved["forecast"]["markets"]],
                ["nikkei", "dow", "usdjpy"],
            )
            self.assertIn("generated_at=2026-10-10T01:15:54+00:00", logs.output[0])
            self.assertIn("market=gold", logs.output[0])
            self.assertIn("target=2026-10-09", logs.output[0])

    def test_all_stale_markets_skip_snapshot_and_rerun_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "forecast.json"
            target = root / "snapshots"
            source.write_text(
                json.dumps({
                    "generated_at": "2026-10-10T23:00:00+00:00",
                    "markets": [
                        {"id": "nikkei", "next_session_date": "2026-10-09"},
                        {"id": "dow", "next_session_date": "2026-10-09"},
                        {"id": "usdjpy", "next_session_date": "2026-10-09"},
                        {"id": "gold", "next_session_date": "2026-10-09"},
                    ],
                }),
                encoding="utf-8",
            )

            with self.assertLogs("scripts.save_live_forecast", level="WARNING"):
                first = save_snapshot(source, target)
                second = save_snapshot(source, target)

            self.assertEqual(first, (None, False))
            self.assertEqual(second, (None, False))
            self.assertFalse(target.exists())

    def test_all_stale_rerun_rejects_existing_valid_snapshot_at_same_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "forecast.json"
            target = root / "snapshots"
            generated_at = "2026-10-10T01:15:54+00:00"
            source.write_text(
                json.dumps({
                    "generated_at": generated_at,
                    "markets": [{
                        "id": "dow",
                        "next_session_date": "2026-10-12",
                        "up_probability": 0.6,
                    }],
                }),
                encoding="utf-8",
            )
            original_path, created = save_snapshot(source, target)
            original_content = original_path.read_text(encoding="utf-8")

            source.write_text(
                json.dumps({
                    "generated_at": generated_at,
                    "markets": [{
                        "id": "dow",
                        "next_session_date": "2026-10-09",
                        "up_probability": 0.4,
                    }],
                }),
                encoding="utf-8",
            )

            with self.assertLogs("scripts.save_live_forecast", level="WARNING"):
                with self.assertRaises(FileExistsError):
                    save_snapshot(source, target)

            self.assertTrue(created)
            self.assertEqual(original_path.read_text(encoding="utf-8"), original_content)
            self.assertEqual(len(list(target.glob("*.json"))), 1)


if __name__ == "__main__":
    unittest.main()
