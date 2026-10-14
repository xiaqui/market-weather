import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts import build_official_scores


class OfficialScoreTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def _record(
        self,
        generated: str,
        market: str = "nikkei",
        target: str = "2026-10-13",
        filename: str | None = None,
        last_data_date: str = "2026-10-09",
    ) -> dict:
        relative_path = filename or f"reports/live-forecast/{generated.replace(':', '-').replace('+', '_')}-{market}.json"
        snapshot = self.root / relative_path
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_text(json.dumps({
            "forecast": {"markets": [{"id": market, "last_data_date": last_data_date}]}
        }), encoding="utf-8")
        return {
            "forecast_file": relative_path,
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
        selected, audit = build_official_scores.select_representatives(records, self.root)
        self.assertEqual(selected[0]["forecast_source_generated_at"], "2026-10-12T16:34:48+00:00")
        self.assertIn("generated_after_session_open", [item["reason"] for item in audit])
        self.assertEqual(sum(item["status"] == "selected" for item in audit), 1)

    def test_falls_back_to_latest_before_open(self):
        records = [self._record("2026-10-12T10:00:00+00:00"), self._record("2026-10-12T14:00:00+00:00")]
        selected, audit = build_official_scores.select_representatives(records, self.root)
        self.assertEqual(selected[0]["forecast_source_generated_at"], "2026-10-12T14:00:00+00:00")
        self.assertIn("latest_before_open_fallback", [item["reason"] for item in audit])

    def test_us_dst_and_session_start_are_explicit(self):
        winter = build_official_scores.session_open("dow", "2026-01-05")
        summer = build_official_scores.session_open("dow", "2026-07-06")
        self.assertEqual(winter.astimezone(ZoneInfo("UTC")).hour, 14)
        self.assertEqual(summer.astimezone(ZoneInfo("UTC")).hour, 13)
        gold = build_official_scores.session_open("gold", "2026-07-06")
        self.assertEqual(gold.date().isoformat(), "2026-07-05")
        self.assertEqual(gold.hour, 18)
        self.assertEqual(build_official_scores.session_open("usdjpy", "2026-07-06").hour, 17)

    def test_fx_and_gold_after_open_are_excluded_in_winter_and_summer(self):
        cases = [
            ("usdjpy", "2026-01-05", "2026-01-04T22:01:00+00:00"),
            ("usdjpy", "2026-07-06", "2026-07-05T21:01:00+00:00"),
            ("gold", "2026-01-05", "2026-01-04T23:01:00+00:00"),
            ("gold", "2026-07-06", "2026-07-05T22:01:00+00:00"),
        ]
        for market, target, generated in cases:
            with self.subTest(market=market, target=target):
                record = self._record(generated, market, target)
                selected, audit = build_official_scores.select_representatives([record], self.root)
                self.assertEqual(selected, [])
                self.assertEqual(audit[0]["reason"], "generated_after_session_open")

    def test_scheduled_fx_forecast_targets_session_before_open_across_dst(self):
        cases = [
            # Sunday's run must forecast Monday, rather than the prior Friday.
            ("2026-01-04T20:00:00+00:00", "2026-01-05", 2),
            ("2026-07-05T20:00:00+00:00", "2026-07-06", 1),
        ]
        for scheduled, target, hours_before_open in cases:
            with self.subTest(target=target):
                generated = datetime.fromisoformat(scheduled)
                opening = build_official_scores.session_open("usdjpy", target)
                self.assertEqual(opening.astimezone(timezone.utc) - generated, timedelta(hours=hours_before_open))
                last_data_date = (
                    "2026-01-02" if target.startswith("2026-01") else "2026-07-03"
                )
                record = self._record(
                    scheduled, "usdjpy", target, last_data_date=last_data_date
                )
                selected, audit = build_official_scores.select_representatives([record], self.root)
                self.assertEqual(selected, [record])
                self.assertEqual(audit[0]["reason"], "latest_00_06_jst")

    def test_delayed_fx_run_cannot_admit_target_session_information(self):
        cases = [
            ("2026-01-05", "2026-01-04T21:59:59+00:00", True),
            ("2026-01-05", "2026-01-04T22:00:00+00:00", False),
            ("2026-07-06", "2026-07-05T20:59:59+00:00", True),
            ("2026-07-06", "2026-07-05T21:00:00+00:00", False),
        ]
        for target, generated, eligible in cases:
            with self.subTest(target=target, generated=generated):
                last_data_date = (
                    "2026-01-02" if target.startswith("2026-01") else "2026-07-03"
                )
                record = self._record(
                    generated, "usdjpy", target, last_data_date=last_data_date
                )
                selected, audit = build_official_scores.select_representatives([record], self.root)
                self.assertEqual(bool(selected), eligible)
                if eligible:
                    self.assertEqual(audit[0]["status"], "selected")
                else:
                    self.assertEqual(audit[0]["reason"], "generated_after_session_open")

    def test_future_input_is_rejected(self):
        record = self._record("2026-10-12T16:34:48+00:00", filename="snapshot.json")
        (self.root / "snapshot.json").write_text(json.dumps({"forecast": {"markets": [{"id": "nikkei", "last_data_date": "2026-10-13"}]}}), encoding="utf-8")
        selected, audit = build_official_scores.select_representatives([record], self.root)
        self.assertEqual(selected, [])
        self.assertEqual(audit[0]["reason"], "future_input_data")

    def test_unverifiable_snapshot_fields_are_excluded_with_specific_reasons(self):
        base = self._record("2026-10-12T16:34:48+00:00", filename="snapshot.json")
        cases = [
            ("snapshot_not_found", None, {**base, "forecast_file": "missing.json"}),
            ("market_not_in_snapshot", {"forecast": {"markets": [{"id": "dow", "last_data_date": "2026-10-09"}]}}, base),
            ("missing_last_data_date", {"forecast": {"markets": [{"id": "nikkei"}]}}, base),
            ("invalid_last_data_date", {"forecast": {"markets": [{"id": "nikkei", "last_data_date": "not-a-date"}]}}, base),
        ]
        for reason, payload, record in cases:
            with self.subTest(reason=reason):
                if payload is not None:
                    (self.root / "snapshot.json").write_text(json.dumps(payload), encoding="utf-8")
                selected, audit = build_official_scores.select_representatives([record], self.root)
                self.assertEqual(selected, [])
                self.assertEqual(audit[0]["reason"], reason)

        unknown = {**base, "market": "unknown"}
        selected, audit = build_official_scores.select_representatives([unknown], self.root)
        self.assertEqual(selected, [])
        self.assertEqual(audit[0]["reason"], "unknown_market_symbol")

    def test_legacy_september_snapshot_without_last_data_date_is_excluded(self):
        history = json.loads((build_official_scores.ROOT / "reports/live-forecast-history.json").read_text(encoding="utf-8"))
        legacy = [record for record in history if record.get("forecast_file") == "reports/live-forecast/2026-09-21.json"]
        selected, audit = build_official_scores.select_representatives(legacy)
        self.assertEqual(selected, [])
        self.assertTrue(legacy)
        self.assertIn("missing_last_data_date", {item["reason"] for item in audit})
        self.assertTrue(all(item["status"] == "excluded" for item in audit))

    def test_build_is_idempotent_and_uses_same_population(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            history = root / "history.json"
            output = root / "official.json"
            records = [self._record("2026-10-12T16:34:48+00:00")]
            history.write_text(json.dumps(records), encoding="utf-8")
            first = build_official_scores.build_report(history, output, self.root)
            first_bytes = output.read_bytes()
            second = build_official_scores.build_report(history, output, self.root)
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
