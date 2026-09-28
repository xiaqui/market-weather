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
            'class="card-numbers"',
            'class="current"',
            'class="icon"',
            'class="card-weather"',
            'class="weather-meta"',
            'class="forecast-support"',
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

    def test_card_and_detail_display_forecast_support_as_percentage(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")
        detail_source = source.split("function renderDetail(market) {", 1)[1].split(
            "globalThis.updateCurrentValues", 1
        )[0]

        self.assertIn("予報根拠度", detail_source)
        self.assertIn("percent(market.forecast_support)", detail_source)
        self.assertIn("Trend一致度", detail_source)
        card_source = source.split("function card(market) {", 1)[1].split(
            "function renderMarkets()", 1
        )[0]
        self.assertIn("percent(market.forecast_support)", card_source)
        self.assertIn('class="forecast-support"', card_source)

    def test_card_uses_two_columns_with_weather_as_largest_element(self) -> None:
        styles = STYLES.read_text(encoding="utf-8")

        self.assertIn(".market-card { display: grid", styles)
        self.assertIn("grid-template-columns: minmax(0, 45fr) minmax(0, 55fr)", styles)
        self.assertIn(".card-numbers {", styles)
        self.assertIn(".card-weather {", styles)
        self.assertIn(".icon {", styles)
        self.assertIn("font-size: clamp(3.35rem, 16vw, 4.45rem)", styles)
        self.assertIn(".range {", styles)
        self.assertIn("font-size: clamp(.58rem, 2.6vw, .7rem)", styles)

    def test_narrow_cards_keep_two_columns_and_favor_number_fit(self) -> None:
        styles = STYLES.read_text(encoding="utf-8")

        narrow_styles = styles.split("@media (max-width: 359px)", 1)[1].split(
            "@media (min-width: 650px)", 1
        )[0]
        self.assertIn("grid-template-columns: minmax(0, 52fr) minmax(0, 48fr)", narrow_styles)

    def test_weather_block_has_no_column_divider(self) -> None:
        styles = STYLES.read_text(encoding="utf-8")
        weather_styles = styles.split(".card-weather {", 1)[1].split("}", 1)[0]

        self.assertNotIn("border-left", weather_styles)

    def test_icon_stays_right_aligned_and_only_meta_is_centered(self) -> None:
        styles = STYLES.read_text(encoding="utf-8")
        icon_styles = styles.split(".icon {", 1)[1].split("}", 1)[0]
        meta_styles = styles.split(".weather-meta {", 1)[1].split("}", 1)[0]

        self.assertIn("justify-self: end", icon_styles)
        self.assertNotIn("justify-self: center", icon_styles)
        self.assertIn("width: clamp(3.35rem, 16vw, 4.45rem)", meta_styles)
        self.assertIn("max-width: 100%", meta_styles)
        self.assertIn("justify-content: center", meta_styles)
        self.assertIn("justify-self: end", meta_styles)

    def test_card_shortens_partly_cloudy_but_detail_keeps_formal_label(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")
        card_source = source.split("function card(market) {", 1)[1].split(
            "function renderMarkets()", 1
        )[0]
        detail_source = source.split("function renderDetail(market) {", 1)[1].split(
            "globalThis.updateCurrentValues", 1
        )[0]

        self.assertIn('partly_cloudy: ["🌤️", "晴れ時々曇り"]', source)
        self.assertIn('value === "partly_cloudy"', source)
        self.assertIn('? "晴時々曇"', source)
        self.assertIn("compactConditionLabel(market.weather)", card_source)
        self.assertIn("safeCondition(market.weather)[1]", detail_source)


if __name__ == "__main__":
    unittest.main()
