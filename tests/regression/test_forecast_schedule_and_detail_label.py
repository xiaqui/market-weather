import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_JS = ROOT / "web/app.js"
WORKFLOW = ROOT / ".github/workflows/update-daily-forecast.yml"


class ForecastScheduleAndDetailLabelTest(unittest.TestCase):
    def test_forecast_runs_after_japan_and_us_market_closes(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('cron: "0 7 * * 1-5"', workflow)
        self.assertIn('cron: "0 20 * * 0-4"', workflow)
        self.assertIn('cron: "30 22 * * 1-5"', workflow)
        self.assertIn("16:00 JST", workflow)
        self.assertIn("17:00 ET", workflow)
        self.assertIn("07:30 JST", workflow)

    def test_detail_uses_baseline_label_until_live_value_exists(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")
        self.assertIn("function detailCurrentLabel(market)", source)
        self.assertIn('liveCurrentValues.has(market.id) ? "現在値" : "基準値"', source)
        self.assertIn("<dt>${detailCurrentLabel(market)}</dt>", source)

    def test_live_update_rerenders_open_detail(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")
        update_source = source.split("globalThis.updateCurrentValues = updates => {", 1)[1].split(
            "function renderCurrentStatus", 1
        )[0]
        self.assertIn("liveCurrentValues.set(update.id, update.current)", update_source)
        self.assertIn("renderDetail(selectedMarket)", update_source)


if __name__ == "__main__":
    unittest.main()
