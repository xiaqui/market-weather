import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class DailyForecastWorkflowTest(unittest.TestCase):
    def test_daily_update_runs_the_existing_forecast_pipeline(self) -> None:
        workflow = (ROOT / ".github/workflows/update-daily-forecast.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn('cron: "30 22 * * 1-5"', workflow)
        self.assertIn('python-version: "3.12"', workflow)
        self.assertIn("python scripts/fetch_market_data.py", workflow)
        self.assertIn("python scripts/sync_forecast.py", workflow)
        snapshot = workflow.index("python -m scripts.save_live_forecast")
        score = workflow.index("python -m scripts.score_live_forecast")
        self.assertLess(snapshot, score)
        self.assertIn(
            "- name: Score prospective forecasts\n"
            "        run: python -m scripts.score_live_forecast",
            workflow,
        )
        self.assertNotIn("python scripts/score_live_forecast.py", workflow)
        self.assertIn("git status --porcelain --", workflow)
        self.assertIn("git push origin HEAD:main", workflow)
        self.assertIn("reports/live-forecast \\", workflow)

    def test_successful_daily_update_triggers_pages_deployment(self) -> None:
        workflow = (ROOT / ".github/workflows/deploy-pages.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("workflow_run:", workflow)
        self.assertIn("workflows: [Update Daily Forecast]", workflow)
        self.assertIn("github.event.workflow_run.conclusion == 'success'", workflow)


if __name__ == "__main__":
    unittest.main()
