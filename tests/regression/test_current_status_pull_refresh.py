import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APP_JS = ROOT / "web/app.js"
INDEX_HTML = ROOT / "web/index.html"
ACTIVITY = ROOT / "android/app/src/main/java/jp/xiaqui/marketweather/MainActivity.java"
YAHOO_FETCH = ROOT / "android/app/src/main/assets/yahoo_fetch.html"


def run_status_scenario(user_agent: str, status_calls: list) -> dict:
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
  "#current-status": {{ hidden: true }},
  "#current-status-line": {{ textContent: "" }},
  "#current-status-detail": {{ textContent: "" }},
  "#current-status-diagnostics": {{ hidden: true }},
  "#current-status-list": {{ children: [], replaceChildren(...nodes) {{ this.children = nodes; }} }},
}};
const forecast = {{
  generated_at: "2026-09-22T00:00:00+00:00",
  markets: [
    {{ id: "nikkei", name: "日経平均", current: 100, weather: "sunny", up_probability: 0.7,
       trend_probability: 0.6, analog_probability: 0.65, analog_count: 30, range_low: 95,
       range_high: 105, confidence: 0.8, risk: "normal", last_data_date: "2026-09-18",
       next_session_date: "2026-09-24" }},
  ],
}};
const context = {{
  console, Intl, Date, Math, Number, String, Map, Array, navigator: {{ userAgent: {json.dumps(user_agent)} }},
  document: {{
    createElement() {{ return {{ innerHTML: "", addEventListener(type, handler) {{ this["on" + type] = handler; }} }}; }},
    querySelector(selector) {{ return elements[selector]; }},
  }},
  fetch: async () => ({{ ok: true, json: async () => forecast }}),
}};
vm.createContext(context);
vm.runInContext(source, context);
vm.runInContext("markets = " + JSON.stringify(forecast.markets) + "; renderMarkets();", context);
const calls = {json.dumps(status_calls)};
for (const call of calls) {{
  context.updateCurrentStatus(call);
}}
process.stdout.write(JSON.stringify({{
  statusHidden: elements["#current-status"].hidden,
  line: elements["#current-status-line"].textContent,
  detail: elements["#current-status-detail"].textContent,
  diagnosticsHidden: elements["#current-status-diagnostics"].hidden,
  diagnosticsCount: elements["#current-status-list"].children.length,
  diagnostics: elements["#current-status-list"].children.map(child => child.textContent),
  weather: forecast.markets[0].weather,
  probability: forecast.markets[0].up_probability,
  rangeLow: forecast.markets[0].range_low,
  current: forecast.markets[0].current,
}}));
""",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(output.stdout)


class CurrentStatusAndroidOnlyTest(unittest.TestCase):
    def test_status_hidden_and_ignored_on_regular_browser(self) -> None:
        rendered = run_status_scenario(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            [{"attempted": True, "total": 4, "successCount": 4, "failedMarkets": [],
              "manualUpdating": False, "lastUpdatedAt": 1700000000000, "quotes": []}],
        )
        self.assertTrue(rendered["statusHidden"])
        self.assertEqual("", rendered["line"])
        # Forecast values are never touched by status updates.
        self.assertEqual("sunny", rendered["weather"])
        self.assertEqual(0.7, rendered["probability"])
        self.assertEqual(95, rendered["rangeLow"])
        self.assertEqual(100, rendered["current"])

    def test_initial_status_shown_immediately_on_android(self) -> None:
        rendered = run_status_scenario(
            "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 MarketWeatherApp/1.0",
            [],
        )
        self.assertFalse(rendered["statusHidden"])
        self.assertIn("確認中", rendered["line"])

    def test_full_success_status_on_android(self) -> None:
        rendered = run_status_scenario(
            "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 MarketWeatherApp/1.0",
            [{"attempted": True, "total": 4, "successCount": 4, "failedMarkets": [],
              "manualUpdating": False, "lastUpdatedAt": 1700000000000,
              "quotes": [{"id": "gold", "ok": True, "price": 4366.1, "timestamp": 1700000000}]}],
        )
        self.assertFalse(rendered["statusHidden"])
        self.assertIn("Yahoo取得成功 4/4", rendered["line"])
        self.assertIn("更新:", rendered["detail"])
        self.assertEqual(
            "GOLD: 成功 regularMarketPrice=4,366.1 regularMarketTime=2023/11/14 22:13:20",
            rendered["diagnostics"][0],
        )

    def test_partial_failure_status_on_android(self) -> None:
        rendered = run_status_scenario(
            "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 MarketWeatherApp/1.0",
            [{"attempted": True, "total": 4, "successCount": 3, "failedMarkets": ["gold"],
              "manualUpdating": False, "lastUpdatedAt": 1700000000000,
              "quotes": [{"id": "gold", "ok": False, "reason": "HTTP 429"}]}],
        )
        self.assertIn("Yahoo取得 3/4", rendered["line"])
        self.assertIn("GOLD取得失敗", rendered["detail"])
        self.assertFalse(rendered["diagnosticsHidden"])
        self.assertEqual(1, rendered["diagnosticsCount"])
        self.assertEqual("GOLD: 失敗 HTTP 429", rendered["diagnostics"][0])

    def test_full_failure_keeps_previous_value_message(self) -> None:
        rendered = run_status_scenario(
            "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 MarketWeatherApp/1.0",
            [{"attempted": True, "total": 4, "successCount": 0,
              "failedMarkets": ["nikkei", "dow", "usdjpy", "gold"],
              "manualUpdating": False, "lastUpdatedAt": 1700000000000, "quotes": []}],
        )
        self.assertIn("Yahoo取得失敗", rendered["line"])
        self.assertIn("前回値を表示中", rendered["detail"])
        # The market's current value is untouched by a total failure.
        self.assertEqual(100, rendered["current"])

    def test_diagnostics_update_on_subsequent_status_calls(self) -> None:
        rendered = run_status_scenario(
            "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 MarketWeatherApp/1.0",
            [
                {"attempted": True, "total": 4, "successCount": 0,
                 "failedMarkets": ["nikkei"], "manualUpdating": True,
                 "quotes": [{"id": "nikkei", "ok": False, "reason": "HTTP 401"}]},
                {"attempted": True, "total": 4, "successCount": 0,
                 "failedMarkets": ["nikkei"], "manualUpdating": False,
                 "quotes": [{"id": "nikkei", "ok": False, "reason": "UnknownHostException: offline"}]},
            ],
        )
        self.assertEqual(["NIKKEI: 失敗 UnknownHostException: offline"], rendered["diagnostics"])
        self.assertIn("Yahoo取得失敗", rendered["line"])

    def test_manual_updating_flag_is_reflected(self) -> None:
        rendered = run_status_scenario(
            "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 MarketWeatherApp/1.0",
            [{"attempted": True, "total": 4, "successCount": 4, "failedMarkets": [],
              "manualUpdating": True, "lastUpdatedAt": 1700000000000, "quotes": []}],
        )
        self.assertIn("更新中", rendered["line"])

    def test_429_cooldown_is_visible_on_android(self) -> None:
        rendered = run_status_scenario(
            "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 MarketWeatherApp/1.0",
            [{"attempted": True, "total": 4, "successCount": 1,
              "failedMarkets": ["dow", "usdjpy", "gold"], "manualUpdating": False,
              "cooldownActive": True, "cooldownUntil": 1700000300000,
              "lastUpdatedAt": 1700000000000,
              "quotes": [{"id": "dow", "ok": False, "reason": "HTTP 429"}]}],
        )
        self.assertIn("HTTP 429 cooldown中", rendered["line"])
        self.assertIn("429 cooldown終了予定:", rendered["detail"])


class AndroidPullToRefreshImplementationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.source = ACTIVITY.read_text(encoding="utf-8")

    def test_user_agent_marker_added_for_web_detection(self) -> None:
        self.assertIn('UA_APP_SUFFIX = " MarketWeatherApp/1.0"', self.source)
        self.assertIn("setUserAgentString(settings.getUserAgentString() + UA_APP_SUFFIX)", self.source)

    def test_touch_listener_drives_pull_to_refresh_without_consuming_scroll(self) -> None:
        self.assertIn("setOnTouchListener", self.source)
        self.assertIn("handlePullToRefreshTouch(event)", self.source)
        self.assertIn("return false;", self.source)
        self.assertIn("webView.getScrollY() <= 0", self.source)
        self.assertIn("triggerManualRefresh()", self.source)

    def test_manual_refresh_reuses_native_yahoo_fetch_and_guards_concurrency(self) -> None:
        self.assertIn("private void triggerManualRefresh()", self.source)
        self.assertIn("if (!polling || fetchInProgress)", self.source)
        self.assertIn("fetchCurrentValues(pollingGeneration, true)", self.source)
        self.assertIn("private boolean fetchInProgress;", self.source)
        self.assertIn("reportCurrentStatus(true);", self.source)

    def test_periodic_polling_is_removed(self) -> None:
        self.assertNotIn("UPDATE_INTERVAL_MS", self.source)
        self.assertNotIn("schedulePolling(", self.source)
        self.assertNotIn("scheduledUpdate", self.source)

    def test_manual_refresh_does_not_reload_forecast_or_webpage(self) -> None:
        self.assertNotIn("webView.reload()", self.source)
        # loadUrl should only be called once, at initial startup.
        self.assertEqual(1, self.source.count("webView.loadUrl("))

    def test_status_bridge_reports_diagnostics_and_completion_state(self) -> None:
        self.assertIn("private void reportCurrentStatus(boolean manualUpdating)", self.source)
        self.assertIn("window.updateCurrentStatus(", self.source)
        self.assertIn('status.put("attempted", lastAttempted)', self.source)
        self.assertIn('status.put("successCount", lastSuccessCount)', self.source)
        self.assertIn('status.put("failedMarkets", failed)', self.source)
        self.assertIn('"lastUpdatedAt"', self.source)
        self.assertIn('status.put("quotes", quotes)', self.source)
        self.assertIn('item.put("reason", diagnostic.reason != null ? diagnostic.reason : JSONObject.NULL)', self.source)


class AndroidYahooDiagnosticsImplementationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.source = ACTIVITY.read_text(encoding="utf-8")
        self.fetch_page = YAHOO_FETCH.read_text(encoding="utf-8")

    def test_yahoo_fetch_uses_isolated_webview_javascript(self) -> None:
        for snippet in (
            'YAHOO_FETCH_PAGE = "file:///android_asset/yahoo_fetch.html"',
            "setAllowUniversalAccessFromFileURLs(true)",
            'addJavascriptInterface(new YahooFetchBridge(), "AndroidYahoo")',
            "window.fetchYahooMarkets(",
            "@JavascriptInterface",
        ):
            self.assertIn(snippet, self.source)
        self.assertNotIn("HttpURLConnection", self.source)

    def test_ap37_style_urls_and_plain_fetch_are_preserved(self) -> None:
        for snippet in (
            "https://query1.finance.yahoo.com/v8/finance/chart/%5EN225",
            "https://query1.finance.yahoo.com/v8/finance/chart/%5EDJI",
            "https://query1.finance.yahoo.com/v8/finance/chart/USDJPY=X",
            "https://query1.finance.yahoo.com/v8/finance/chart/GC=F",
            "await fetch(url)",
            "meta.regularMarketPrice",
            "meta.regularMarketTime",
        ):
            self.assertIn(snippet, self.fetch_page)

    def test_each_market_fetch_has_a_timeout_and_continues_after_abort(self) -> None:
        for snippet in (
            "FETCH_TIMEOUT_MS = 10_000",
            "new AbortController()",
            "controller.abort()",
            "signal: controller.signal",
            'error.name === "AbortError"',
            'reason: timedOut ? `timeout ${FETCH_TIMEOUT_MS}ms`',
            "clearTimeout(timeoutId)",
        ):
            self.assertIn(snippet, self.fetch_page)

    def test_429_stops_cycle_and_persists_cooldown(self) -> None:
        for snippet in (
            "MARKET_REQUEST_SPACING_MS = 1_500L",
            "RATE_LIMIT_COOLDOWN_MS = 5 * 60_000L",
            'item.optBoolean("rateLimited", false)',
            "setRateLimitCooldownUntil(triggeredCooldownUntil)",
            "getSharedPreferences(PREFS_NAME, MODE_PRIVATE)",
        ):
            self.assertIn(snippet, self.source)
        for snippet in (
            "response.status === 429",
            '"HTTP 429 cooldown中（未取得）"',
            "break;",
        ):
            self.assertIn(snippet, self.fetch_page)

    def test_rotation_restore_skips_immediate_refetch(self) -> None:
        self.assertIn("skipNextResumeFetch = savedInstanceState != null", self.source)
        self.assertIn("if (skipNextResumeFetch)", self.source)


class IndexHtmlCurrentStatusMarkupTest(unittest.TestCase):
    def test_current_status_section_exists_and_hidden_by_default(self) -> None:
        html = INDEX_HTML.read_text(encoding="utf-8")
        self.assertIn('id="current-status"', html)
        self.assertIn('id="current-status"', html.split("markets")[0])
        self.assertIn("hidden", html.split('id="current-status"')[1].split(">")[0])


if __name__ == "__main__":
    unittest.main()
