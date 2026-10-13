import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts import build_official_scores


class OfficialScoreTest(unittest.TestCase):
    def _record(self, generated: str, market: str = "nikkei", target: str = "2026-10-13", filename: str | None = None) -> dict:
        return {
            "forecast_file": filename or f"reports/live-forecast/{generated[11:19].replace(':', '')}.json",
            "forecast_source_generated_at": generated,
            "market": market,
            "target_session_date": target,
            "trend_probability": .6,
            "analog_probability": .4,
            "ensemble_probability": .7,
            "actual_direction": "up",
            "predicted_range_low": 90,
            "predicted_range_high": 110,
            "actual_close": 100,
        }

    def test_selects_last_midnight_candidate_and_excludes_after_open(self):
        records = [
            self._record("2026-10-12T14:00:00+00:00"),
            self._record("2026-10-12T16:34:48+00:00"),  # 01:34:48 JST
            self._record("2026-10-13T03:05:00+00:00"),  # 12:05 JST, after open
        ]
        selected, audit = build_official_scores.select_representatives(records)
        self.assertEqual(selected[0]["forecast_source_generated_at"], "2026-10-12T16:34:48+00:00")
        self.assertIn("generated_after_session_open", [item["reason"] for item in audit])
        self.assertEqual(sum(item["status"] == "selected" for item in audit), 1)

    def test_falls_back_to_latest_before_open(self):
        records = [self._record("2026-10-12T10:00:00+00:00"), self._record("2026-10-12T14:00:00+00:00")]
        selected, audit = build_official_scores.select_representatives(records)
        self.assertEqual(selected[0]["forecast_source_generated_at"], "2026-10-12T14:00:00+00:00")
        self.assertIn("latest_before_open_fallback", [item["reason"] for item in audit])

    def test_us_dst_and_session_start_are_explicit(self):
        winter = build_official_scores.session_open("dow", "2026-01-05")
        summer = build_official_scores.session_open("dow", "2026-07-06")
        self.assertEqual(winter.astimezone(ZoneInfo("UTC")).hour, 14)
        self.assertEqual(summer.astimezone(ZoneInfo("UTC")).hour, 13)
        gold = build_official_scores.session_open("gold", "2026-07-06")
        self.assertEqual(gold.date().isoformat(), "2026-07-05")

    def test_future_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = self._record("2026-10-12T16:34:48+00:00", filename="snapshot.json")
            (root / "snapshot.json").write_text(json.dumps({"forecast": {"markets": [{"id": "nikkei", "last_data_date": "2026-10-13"}]}}), encoding="utf-8")
            selected, audit = build_official_scores.select_representatives([record], root)
        self.assertEqual(selected, [])
        self.assertEqual(audit[0]["reason"], "future_input_data")

    def test_build_is_idempotent_and_uses_same_population(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            history = root / "history.json"
            output = root / "official.json"
            records = [self._record("2026-10-12T16:34:48+00:00")]
            history.write_text(json.dumps(records), encoding="utf-8")
            first = build_official_scores.build_report(history, output, root)
            first_bytes = output.read_bytes()
            second = build_official_scores.build_report(history, output, root)
        self.assertEqual(first, second)
        self.assertEqual(first_bytes, json.dumps(second, ensure_ascii=False, indent=2).encode() + b"\n")
        samples = {value["samples"] for value in first["overall"]["forecasters"].values()}
        self.assertEqual(samples, {1})
        self.assertIsNone(first["overall"]["range"]["mean_interval_score"])

    def test_missing_probabilities_and_empty_data_are_na(self):
        empty = build_official_scores._metrics([])
        missing = build_official_scores._metrics([{**self._record("2026-10-12T16:34:48+00:00"), "analog_probability": None}])
        self.assertIsNone(empty["forecasters"]["trend"]["accuracy"])
        self.assertEqual(missing["comparison_population"], 0)


if __name__ == "__main__":
    unittest.main()
