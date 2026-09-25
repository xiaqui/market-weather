import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APP_JS = ROOT / "web/app.js"
INDEX = ROOT / "web/index.html"
STYLES = ROOT / "web/styles.css"


class CompactWebUiTest(unittest.TestCase):
    def test_card_keeps_only_primary_forecast_fields(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")
        card_source = source.split("function card(market) {", 1)[1].split("function renderMarkets()", 1)[0]

        for snippet in (
            'class="current"',
            'class="icon"',
            'class="forecast-copy"',
            'class="forecast-summary"',
            '<span class="range-label">予想</span>',
        ):
            self.assertIn(snippet, card_source)

        self.assertNotIn("予想レンジ", card_source)
        self.assertNotIn("上昇確率", card_source)
        self.assertNotIn("信頼度", card_source)
        self.assertNotIn("リスク", card_source)

    def test_announcement_time_is_shown_beside_heading_in_jst(self) -> None:
        html = INDEX.read_text(encoding="utf-8")
        source = APP_JS.read_text(encoding="utf-8")

        self.assertIn(
            '<h1>次営業日の金融予報 <span id="generated">読み込み中…</span></h1>',
            html,
        )
        self.assertIn('timeZone: "Asia/Tokyo"', source)
        self.assertIn('weekday: "short"', source)
        self.assertIn('${part("month")}/${part("day")}(${part("weekday")})', source)
        self.assertIn("announcementTime(forecast.generated_at)", source)
        self.assertNotIn('.replace("/", "月")', source)
        self.assertIn("発表", source)

    def test_announcement_time_includes_japanese_weekday(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")
        function_source = source.split("const announcementTime =", 1)[1].split(
            "const safeCondition", 1
        )[0]
        result = subprocess.run(
            [
                "node",
                "-e",
                f"const announcementTime = {function_source} "
                'process.stdout.write(announcementTime("2026-09-25T02:11:00Z"));',
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertEqual("9/25(金) 11:11", result.stdout)

    def test_live_direction_includes_percentage(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")

        self.assertIn("const livePercent", source)
        self.assertIn("↑ ${amount}", source)
        self.assertIn("ー ${amount}", source)
        self.assertIn("↓ ${amount}", source)

    def test_detail_labels_confidence_as_non_probability(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")
        detail_source = source.split("function renderDetail(market) {", 1)[1].split(
            "globalThis.updateCurrentValues", 1
        )[0]

        self.assertIn("予報信頼度（的中確率ではありません）", detail_source)
        self.assertIn("percent(market.confidence)", detail_source)

    def test_weather_label_is_left_aligned_but_range_stays_right_aligned(self) -> None:
        styles = STYLES.read_text(encoding="utf-8")

        self.assertIn(".icon {", styles)
        self.assertIn("font-size: 2.75rem", styles)
        self.assertIn(".weather-name { justify-self: start;", styles)
        self.assertIn(".range {", styles)
        self.assertIn("text-align: right", styles)


if __name__ == "__main__":
    unittest.main()
