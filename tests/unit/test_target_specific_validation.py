import unittest

from scripts import fetch_market_data as model
from scripts import validate_target_specific as experiment


def rows(count=30, offset=0, missing=()):
    return [model.Candle(1_700_000_000 + index * 86_400, 100 + index + offset,
                         100 + index + offset, 100 + index + offset,
                         100 + index + offset, None)
            for index in range(count) if index not in missing]


class TargetSpecificValidationTest(unittest.TestCase):
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

    def test_report_is_deterministic_apart_from_generation_time(self):
        production = {market: rows(80, index) for index, market in enumerate(model.MARKET_ORDER)}
        symbols = {symbol for target in experiment.MATERIALS.values() for symbol, _ in target}
        materials = {symbol: rows(80, index) for index, symbol in enumerate(sorted(symbols))}
        left = experiment.build_report(production, materials)
        right = experiment.build_report(production, materials)
        left.pop("generated_at")
        right.pop("generated_at")
        self.assertEqual(left, right)


if __name__ == "__main__":
    unittest.main()
