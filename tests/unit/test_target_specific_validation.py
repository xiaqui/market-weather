import unittest
from datetime import datetime, timezone
from dataclasses import replace

from scripts import fetch_market_data as model
from scripts import validate_target_specific as experiment


def rows(count=30, offset=0, missing=()):
    return [model.Candle(1_700_000_000 + index * 86_400, 100 + index + offset,
                         100 + index + offset, 100 + index + offset,
                         100 + index + offset, None)
            for index in range(count) if index not in missing]


class TargetSpecificValidationTest(unittest.TestCase):
    def test_normalization_preserves_utc_session_date_and_availability_clock(self):
        raw = model.Candle(1_704_067_200, 1, 1, 1, 1, None)  # 2024-01-01 00:00 UTC
        expected = {
            "^VIX": (2024, 1, 1, 21, 15),
            "^IXIC": (2024, 1, 1, 21, 0),
            "^TNX": (2024, 1, 1, 21, 0),
            "DX-Y.NYB": (2024, 1, 1, 22, 0),
        }
        for symbol, parts in expected.items():
            with self.subTest(symbol=symbol):
                normalized = experiment.normalize_experimental_closes(symbol, [raw])[0]
                instant = datetime.fromtimestamp(normalized.timestamp, timezone.utc)
                self.assertEqual((instant.year, instant.month, instant.day,
                                  instant.hour, instant.minute), parts)

    def test_symbol_mapping_has_exactly_three_distinct_materials_per_market(self):
        self.assertEqual(set(experiment.MATERIALS), set(model.MARKET_ORDER))
        for target in model.MARKET_ORDER:
            symbols = experiment.target_material_symbols(target)
            self.assertEqual(len(symbols), 3)
            self.assertEqual(len(set(symbols)), 3)

    def test_state_uses_target_specific_inputs_and_never_future_row(self):
        histories = {symbol: rows(offset=index) for index, symbol in enumerate(
            experiment.target_material_symbols("gold"))}
        clock = histories["^VIX"][-2].timestamp
        baseline = experiment.material_state_at(histories, clock, "gold")
        histories["^VIX"][-1] = model.Candle(histories["^VIX"][-1].timestamp,
                                               9999, 9999, 9999, 9999, None)
        self.assertEqual(baseline, experiment.material_state_at(histories, clock, "gold"))
        self.assertEqual(len(baseline.vector), 15)

    def test_missing_session_uses_last_completed_observation(self):
        symbols = experiment.target_material_symbols("dow")
        complete = {symbol: rows() for symbol in symbols}
        missing = dict(complete)
        missing[symbols[0]] = rows(missing=(28,))
        clock = complete[symbols[0]][-1].timestamp
        self.assertIsNotNone(experiment.material_state_at(missing, clock, "dow"))

    def test_insufficient_material_history_skips_state(self):
        histories = {symbol: rows() for symbol in experiment.target_material_symbols("nikkei")}
        histories["GC=F"] = rows(20)
        self.assertIsNone(experiment.material_state_at(histories, 2_000_000_000, "nikkei"))

    def test_every_record_audits_material_boundary_including_equal_clock(self):
        production = {market: rows(70, index) for index, market in enumerate(model.MARKET_ORDER)}
        materials = {symbol: rows(70, index) for index, symbol in enumerate(
            experiment.target_material_symbols("gold"))}
        records = experiment.walk_target_specific(production, materials, "gold", sessions=30)
        self.assertTrue(records)
        target_by_timestamp = {row.timestamp: index for index, row in enumerate(production["gold"])}
        for record in records:
            target_index = target_by_timestamp[record.timestamp]
            self.assertLessEqual(record.max_material_timestamp, record.forecast_clock)
            self.assertLessEqual(
                production["gold"][target_index - 1].timestamp, record.forecast_clock
            )
            self.assertLess(record.forecast_clock, record.timestamp)
        # bisect_right makes a row exactly at the forecast clock eligible.
        clock = materials["^VIX"][-1].timestamp
        self.assertEqual(experiment.max_material_timestamp_at(materials, clock, "gold"), clock)

    def test_stale_material_clock_advances_to_known_previous_target_close(self):
        production = {market: rows(70, index) for index, market in enumerate(model.MARKET_ORDER)}
        symbols = experiment.target_material_symbols("gold")
        materials = {symbol: rows(70, index, missing=(48,))
                     for index, symbol in enumerate(symbols)}
        records = experiment.walk_target_specific(production, materials, "gold", sessions=30)
        target = production["gold"]
        record = next(item for item in records if item.timestamp == target[49].timestamp)
        self.assertEqual(record.forecast_clock, target[48].timestamp)
        self.assertLess(record.max_material_timestamp, record.forecast_clock)

    def test_future_target_close_cannot_change_earlier_analog_forecast(self):
        production = {market: rows(90, index) for index, market in enumerate(model.MARKET_ORDER)}
        materials = {symbol: rows(90, index) for index, symbol in enumerate(
            experiment.target_material_symbols("gold"))}
        baseline = experiment.walk_target_specific(production, materials, "gold", sessions=50)
        cutoff = baseline[-5].timestamp
        changed = dict(production)
        changed_rows = list(production["gold"])
        for index, row in enumerate(changed_rows):
            if row.timestamp > cutoff:
                changed_rows[index] = replace(row, open=row.open * 10, high=row.high * 10,
                                              low=row.low * 10, close=row.close * 10)
        changed["gold"] = changed_rows
        rerun = experiment.walk_target_specific(changed, materials, "gold", sessions=50)
        before = [(r.timestamp, r.analog_probability) for r in baseline if r.timestamp <= cutoff]
        after = [(r.timestamp, r.analog_probability) for r in rerun if r.timestamp <= cutoff]
        self.assertEqual(before, after)

    def test_pairing_rejects_actual_mismatch_and_windows_share_membership(self):
        production = {market: rows(320, index) for index, market in enumerate(model.MARKET_ORDER)}
        symbols = {symbol for target in experiment.MATERIALS.values() for symbol, _ in target}
        materials = {symbol: rows(320, index) for index, symbol in enumerate(sorted(symbols))}
        report = experiment.build_report(production, materials, evaluation_timestamp=2_000_000_000)
        for market in report["markets"].values():
            for window in market["windows"]:
                self.assertEqual(window["common"]["sample_count"],
                                 window["target_specific"]["sample_count"])
                self.assertEqual(window["common"]["start_timestamp"],
                                 window["target_specific"]["start_timestamp"])
                self.assertEqual(window["common"]["end_timestamp"],
                                 window["target_specific"]["end_timestamp"])
                self.assertTrue(all(window["pairing"].values()))
        record = model.BacktestRecord(1, .5, .5, .5, True, 1, .1)
        mismatch = replace(record, actual_up=False)
        with self.assertRaises(ValueError):
            experiment._paired([record], [mismatch])

    def test_oos_report_excludes_boundary_and_pairs_identical_outcomes(self):
        production = {market: rows(90, index) for index, market in enumerate(model.MARKET_ORDER)}
        symbols = {symbol for target in experiment.MATERIALS.values() for symbol, _ in target}
        materials = {symbol: rows(90, index) for index, symbol in enumerate(sorted(symbols))}
        boundary = production["nikkei"][-4].timestamp
        evaluation = production["nikkei"][-1].timestamp
        report = experiment.build_oos_report(
            production, materials, boundary, evaluation_timestamp=evaluation
        )
        for market in report["markets"].values():
            self.assertEqual(market["sample_count"], 3)
            self.assertTrue(all(market["pairing"].values()))
            self.assertGreater(market["common"]["start_timestamp"], boundary)
            self.assertEqual(
                market["outcome_dates_utc"],
                [datetime.fromtimestamp(boundary + offset * 86_400, timezone.utc).date().isoformat()
                 for offset in range(1, 4)],
            )
            self.assertIn("analog", market["target_specific_minus_common"]["accuracy"])
            self.assertIn("ensemble", market["target_specific_minus_common"]["brier"])

    def test_oos_report_rejects_non_future_evaluation(self):
        with self.assertRaises(ValueError):
            experiment.build_oos_report({}, {}, 100, evaluation_timestamp=100)

    def test_report_is_deterministic_apart_from_generation_time(self):
        production = {market: rows(80, index) for index, market in enumerate(model.MARKET_ORDER)}
        symbols = {symbol for target in experiment.MATERIALS.values() for symbol, _ in target}
        materials = {symbol: rows(80, index) for index, symbol in enumerate(sorted(symbols))}
        left = experiment.build_report(production, materials, evaluation_timestamp=2_000_000_000)
        right = experiment.build_report(production, materials, evaluation_timestamp=2_000_000_000)
        self.assertEqual(left, right)


if __name__ == "__main__":
    unittest.main()
