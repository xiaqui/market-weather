import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APP_JS = ROOT / "web/app.js"
ACTIVITY = ROOT / "android/app/src/main/java/jp/xiaqui/marketweather/MainActivity.java"
YAHOO_FETCH = ROOT / "android/app/src/main/assets/yahoo_fetch.html"


class LiveCurrentUpdatesTest(unittest.TestCase):
    def test_web_updates_only_current_in_cards_and_open_detail(self) -> None:
        output = subprocess.run(
            [
                "node",
                "-e",
                f"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync({json.dumps(str(APP_JS))}, "utf8");
const elements = {{
  "#detail-content": {{ innerHTML: "" }},
  "#detail": {{ open: false, showModal() {{ this.open = true; }}, close() {{ this.open = false; }} }},
  "#close-detail": {{ addEventListener(type, handler) {{ this["on" + type] = handler; }} }},
  "#generated": {{ textContent: "", hidden: false }},
  "#markets": {{ children: [], replaceChildren(...nodes) {{ this.children = nodes; }} }},
  "#error": {{ hidden: true }},
}};
const forecast = {{
  generated_at: "2026-09-22T00:00:00+00:00",
  markets: [
    {{ id: "nikkei", name: "日経平均", current: 100, weather: "sunny", up_probability: 0.7,
       trend_probability: 0.6, analog_probability: 0.65, analog_count: 30, range_low: 95,
       range_high: 105, confidence: 0.8, risk: "normal", last_data_date: "2026-09-18",
       next_session_date: "2026-09-24" }},
    {{ id: "dow", name: "NYダウ", current: 200, weather: "cloudy", up_probability: 0.5,
       trend_probability: 0.5, analog_probability: 0.5, analog_count: 20, range_low: 190,
       range_high: 210, confidence: 0.7, risk: "caution", last_data_date: "2026-09-21",
       next_session_date: "2026-09-24" }},
  ],
}};
const context = {{
  console, Intl, Date, Math, Number, String, Map, Array,
  document: {{
    createElement() {{ return {{ innerHTML: "", addEventListener(type, handler) {{ this["on" + type] = handler; }} }}; }},
    querySelector(selector) {{ return elements[selector]; }},
  }},
  fetch: async () => ({{ ok: true, json: async () => forecast }}),
}};
vm.createContext(context);
vm.runInContext(source, context);
vm.runInContext("markets = " + JSON.stringify(forecast.markets) + "; renderMarkets();", context);
context.updateCurrentValues([{{ id: "nikkei", current: 111 }}, {{ id: "unknown", current: 999 }}]);
elements["#markets"].children[0].onclick();
context.updateCurrentValues([{{ id: "nikkei", current: 112 }}]);
process.stdout.write(JSON.stringify({{
  nikkeiCard: elements["#markets"].children[0].innerHTML,
  dowCard: elements["#markets"].children[1].innerHTML,
  detail: elements["#detail-content"].innerHTML,
  weather: forecast.markets[0].weather,
  probability: forecast.markets[0].up_probability,
  rangeLow: forecast.markets[0].range_low,
}}));
""",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        rendered = json.loads(output.stdout)

        self.assertIn("112", rendered["nikkeiCard"])
        self.assertIn("112", rendered["detail"])
        self.assertIn("200", rendered["dowCard"])
        self.assertEqual("sunny", rendered["weather"])
        self.assertEqual(0.7, rendered["probability"])
        self.assertEqual(95, rendered["rangeLow"])

    def test_android_live_direction_markers_use_point_one_percent_deadband(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")
        for snippet in (
            "LIVE_DIRECTION_NEUTRAL_THRESHOLD = 0.001",
            "Math.abs(changeRatio) <= LIVE_DIRECTION_NEUTRAL_THRESHOLD",
            "live-direction-flat",
            "live-direction-up",
            "live-direction-down",
            "forecast_current: market.current",
        ):
            self.assertIn(snippet, source)

    def test_last_successful_quotes_are_persisted_and_failures_do_not_clear_them(self) -> None:
        source = ACTIVITY.read_text(encoding="utf-8")
        for snippet in (
            'PREF_QUOTE_PRICE_PREFIX = "quote_price_"',
            'PREF_QUOTE_TIME_PREFIX = "quote_time_"',
            "loadPersistedQuotes();",
            "persistQuote(quote);",
            "latestQuotes.put(quote.marketId, quote)",
        ):
            self.assertIn(snippet, source)
        self.assertNotIn("latestQuotes.clear()", source)

    def test_android_uses_webview_fetch_generation_and_quote_cache(self) -> None:
        source = ACTIVITY.read_text(encoding="utf-8")
        fetch_page = YAHOO_FETCH.read_text(encoding="utf-8")

        for market_id, symbol in {
            "nikkei": "^N225",
            "dow": "^DJI",
            "usdjpy": "JPY=X",
            "gold": "GC=F",
        }.items():
            self.assertIn(f'symbols.put("{market_id}", "{symbol}")', source)
        self.assertIn("protected void onResume()", source)
        self.assertIn("protected void onPause()", source)
        self.assertIn("private long pollingGeneration;", source)
        self.assertIn("private boolean isActiveGeneration(long generation)", source)
        self.assertIn("generation == pollingGeneration", source)
        self.assertIn("fetchCurrentValues(pollingGeneration, false)", source)
        self.assertNotIn("schedulePolling(", source)
        self.assertNotIn("UPDATE_INTERVAL_MS", source)
        self.assertIn("MARKET_REQUEST_SPACING_MS", source)
        self.assertIn("RATE_LIMIT_COOLDOWN_MS", source)
        self.assertIn("setAllowUniversalAccessFromFileURLs(true)", source)
        self.assertIn("window.fetchYahooMarkets(", source)
        self.assertIn("latestQuotes.put(quote.marketId, quote)", source)
        self.assertNotIn("latestQuotes.clear()", source)
        self.assertIn("latestQuotes.values()", source)
        self.assertIn("window.updateCurrentValues(", source)
        self.assertIn("meta.regularMarketPrice", fetch_page)
        self.assertIn("meta.regularMarketTime", fetch_page)


if __name__ == "__main__":
    unittest.main()
