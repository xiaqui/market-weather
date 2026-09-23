import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APP_JS = ROOT / "web/app.js"
INDEX = ROOT / "web/index.html"


class CompactWebUiTest(unittest.TestCase):
    def test_card_keeps_only_primary_forecast_fields(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")
        card_source = source.split("function card(market) {", 1)[1].split("function renderMarkets()", 1)[0]

        for snippet in (
            'class="current"',
            'class="condition"',
            'class="compact-forecast"',
            "上昇確率",
            "予想レンジ",
        ):
            self.assertIn(snippet, card_source)

        self.assertNotIn("信頼度", card_source)
        self.assertNotIn("リスク", card_source)

    def test_announcement_time_is_shown_beside_heading_in_jst(self) -> None:
        html = INDEX.read_text(encoding="utf-8")
        source = APP_JS.read_text(encoding="utf-8")

        self.assertIn(
            '<h1>次営業日の金融天気予報 <span id="generated">読み込み中…</span></h1>',
            html,
        )
        self.assertIn('timeZone: "Asia/Tokyo"', source)
        self.assertIn("announcementTime(forecast.generated_at)", source)
        self.assertIn("発表", source)

    def test_live_direction_includes_percentage(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")

        self.assertIn("const livePercent", source)
        self.assertIn("↑ ${amount}", source)
        self.assertIn("ー ${amount}", source)
        self.assertIn("↓ ${amount}", source)


if __name__ == "__main__":
    unittest.main()
