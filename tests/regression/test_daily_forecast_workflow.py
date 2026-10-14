import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class DailyForecastWorkflowTest(unittest.TestCase):
    def test_daily_update_runs_the_existing_forecast_pipeline(self) -> None:
        workflow = (ROOT / ".github/workflows/update-daily-forecast.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn('cron: "0 20 * * 0-4"', workflow)
        self.assertIn('cron: "30 22 * * 1-5"', workflow)
        self.assertIn('python-version: "3.12"', workflow)
        self.assertIn("python scripts/fetch_market_data.py", workflow)
        self.assertIn(
            "github.event.schedule == '0 20 * * 0-4' && '--advance-usdjpy-target'",
            workflow,
        )
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

    def test_pages_rebuilds_official_scores_before_upload(self) -> None:
        workflow = (ROOT / ".github/workflows/deploy-pages.yml").read_text(
            encoding="utf-8"
        )

        build = workflow.index("python3 -m scripts.build_official_scores")
        upload = workflow.index("actions/upload-pages-artifact@v3")
        deploy = workflow.index("actions/deploy-pages@v4")
        self.assertLess(build, upload)
        self.assertLess(upload, deploy)

    def test_pages_score_build_failure_is_not_ignored(self) -> None:
        workflow = (ROOT / ".github/workflows/deploy-pages.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("run: python3 -m scripts.build_official_scores", workflow)
        self.assertNotIn("continue-on-error", workflow)
        self.assertNotIn("python3 -m scripts.build_official_scores ||", workflow)

    def test_history_and_scoring_logic_changes_trigger_pages_rebuild(self) -> None:
        workflow = (ROOT / ".github/workflows/deploy-pages.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("scripts/build_official_scores.py", workflow)
        self.assertIn("reports/live-forecast-history.json", workflow)

    def test_normal_forecast_update_rebuilds_without_deploy_commit_loop(self) -> None:
        workflow = (ROOT / ".github/workflows/deploy-pages.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("web/**", workflow)
        self.assertIn("shared/forecast.json", workflow)
        self.assertIn("python3 scripts/sync_forecast.py", workflow)
        self.assertNotIn("git commit", workflow)
        self.assertNotIn("git push", workflow)


if __name__ == "__main__":
    unittest.main()
