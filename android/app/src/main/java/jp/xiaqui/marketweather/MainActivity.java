package jp.xiaqui.marketweather;

import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Bundle;
import android.view.MotionEvent;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class MainActivity extends Activity {
    private static final String START_URL = "https://xiaqui.github.io/market-weather/";
    private static final String UA_APP_SUFFIX = " MarketWeatherApp/1.0";
    private static final long MARKET_REQUEST_SPACING_MS = 1_500L;
    private static final long RATE_LIMIT_COOLDOWN_MS = 5 * 60_000L;
    private static final String PREFS_NAME = "market_weather_current";
    private static final String PREF_COOLDOWN_UNTIL = "yahoo_cooldown_until";
    private static final float PULL_REFRESH_THRESHOLD_DP = 96f;
    private static final String YAHOO_FETCH_PAGE = "file:///android_asset/yahoo_fetch.html";
    private static final Map<String, String> MARKET_SYMBOLS = createMarketSymbols();

    private WebView webView;
    private WebView fetchWebView;
    private final Map<String, MarketQuote> latestQuotes = new LinkedHashMap<>();
    private boolean polling;
    private long pollingGeneration;
    private boolean fetchInProgress;
    private boolean lastAttempted;
    private int lastSuccessCount;
    private List<String> lastFailedMarkets = new ArrayList<>();
    private List<MarketStatus> lastDiagnostics = new ArrayList<>();
    private long lastUpdatedAtMillis;
    private long lastCooldownUntilMillis;
    private boolean skipNextResumeFetch;
    private boolean fetchPageReady;
    private long pendingFetchGeneration = -1L;
    private float pullStartY;
    private boolean pullEligible;
    private float pullRefreshThresholdPx;

    private static Map<String, String> createMarketSymbols() {
        Map<String, String> symbols = new LinkedHashMap<>();
        symbols.put("nikkei", "^N225");
        symbols.put("dow", "^DJI");
        symbols.put("usdjpy", "JPY=X");
        symbols.put("gold", "GC=F");
        return Collections.unmodifiableMap(symbols);
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        webView = new WebView(this);
        setContentView(webView);

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setBuiltInZoomControls(true);
        settings.setDisplayZoomControls(false);
        settings.setLoadWithOverviewMode(true);
        settings.setUseWideViewPort(true);
        settings.setUserAgentString(settings.getUserAgentString() + UA_APP_SUFFIX);

        pullRefreshThresholdPx = PULL_REFRESH_THRESHOLD_DP * getResources().getDisplayMetrics().density;

        CookieManager cookieManager = CookieManager.getInstance();
        cookieManager.setAcceptCookie(true);
        cookieManager.setAcceptThirdPartyCookies(webView, true);

        setupYahooFetchWebView();

        webView.setWebChromeClient(new WebChromeClient());

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                return handleUrl(url);
            }

            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                return handleUrl(request.getUrl().toString());
            }

            @Override
            public void onReceivedError(
                    WebView view,
                    WebResourceRequest request,
                    WebResourceError error
            ) {
                super.onReceivedError(view, request, error);
                if (request != null && request.isForMainFrame()) {
                    String url = request.getUrl() != null
                            ? request.getUrl().toString()
                            : "(unknown URL)";
                    showError(
                            "WebView load error",
                            "code=" + error.getErrorCode() + "\n"
                                    + error.getDescription() + "\n\n" + url
                    );
                }
            }

            @Override
            public void onReceivedHttpError(
                    WebView view,
                    WebResourceRequest request,
                    WebResourceResponse errorResponse
            ) {
                super.onReceivedHttpError(view, request, errorResponse);
                if (request != null && request.isForMainFrame()) {
                    String url = request.getUrl() != null
                            ? request.getUrl().toString()
                            : "(unknown URL)";
                    showError(
                            "HTTP error",
                            "status=" + errorResponse.getStatusCode() + "\n\n" + url
                    );
                }
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                applyLatestQuotes();
            }
        });

        webView.setOnTouchListener((view, event) -> {
            handlePullToRefreshTouch(event);
            return false;
        });

        skipNextResumeFetch = savedInstanceState != null;
        if (savedInstanceState == null) {
            webView.loadUrl(START_URL);
        } else {
            webView.restoreState(savedInstanceState);
        }
    }

    private void handlePullToRefreshTouch(MotionEvent event) {
        switch (event.getActionMasked()) {
            case MotionEvent.ACTION_DOWN:
                pullStartY = event.getRawY();
                pullEligible = webView.getScrollY() <= 0;
                break;
            case MotionEvent.ACTION_MOVE:
                if (pullEligible) {
                    if (webView.getScrollY() > 0) {
                        pullEligible = false;
                    } else if (event.getRawY() - pullStartY > pullRefreshThresholdPx) {
                        pullEligible = false;
                        triggerManualRefresh();
                    }
                }
                break;
            case MotionEvent.ACTION_UP:
            case MotionEvent.ACTION_CANCEL:
                pullEligible = false;
                break;
            default:
                break;
        }
    }

    private void triggerManualRefresh() {
        if (!polling || fetchInProgress) {
            return;
        }
        reportCurrentStatus(true);
        fetchCurrentValues(pollingGeneration, true);
    }

    @Override
    protected void onResume() {
        super.onResume();
        polling = true;
        pollingGeneration++;
        if (skipNextResumeFetch) {
            skipNextResumeFetch = false;
            return;
        }
        fetchCurrentValues(pollingGeneration, false);
    }

    @Override
    protected void onPause() {
        polling = false;
        pollingGeneration++;
        super.onPause();
    }

    private boolean isActiveGeneration(long generation) {
        return polling && generation == pollingGeneration;
    }

    private void fetchCurrentValues(long generation, boolean manual) {
        if (!isActiveGeneration(generation) || fetchInProgress) {
            return;
        }

        long now = System.currentTimeMillis();
        long cooldownUntil = getRateLimitCooldownUntil();
        if (now < cooldownUntil) {
            reportCooldownStatus(cooldownUntil);
            return;
        }

        if (!fetchPageReady) {
            pendingFetchGeneration = generation;
            return;
        }

        startYahooFetch(generation);
    }

    private void startYahooFetch(long generation) {
        if (!isActiveGeneration(generation) || fetchInProgress || !fetchPageReady) {
            return;
        }
        fetchInProgress = true;
        fetchWebView.evaluateJavascript(
                "window.fetchYahooMarkets(" + generation + "," + MARKET_REQUEST_SPACING_MS + ");",
                null
        );
    }

    private void setupYahooFetchWebView() {
        fetchWebView = new WebView(this);
        WebSettings fetchSettings = fetchWebView.getSettings();
        fetchSettings.setJavaScriptEnabled(true);
        fetchSettings.setAllowFileAccess(true);
        fetchSettings.setAllowFileAccessFromFileURLs(true);
        fetchSettings.setAllowUniversalAccessFromFileURLs(true);

        // This WebView loads only our packaged asset. Universal file access is intentionally
        // isolated here so the visible GitHub Pages WebView keeps normal browser security.
        fetchWebView.addJavascriptInterface(new YahooFetchBridge(), "AndroidYahoo");
        fetchWebView.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                fetchPageReady = true;
                if (pendingFetchGeneration >= 0) {
                    long generation = pendingFetchGeneration;
                    pendingFetchGeneration = -1L;
                    startYahooFetch(generation);
                }
            }
        });
        fetchWebView.loadUrl(YAHOO_FETCH_PAGE);
    }

    private final class YahooFetchBridge {
        @JavascriptInterface
        public void onResult(long generation, String payload) {
            runOnUiThread(() -> handleYahooFetchResult(generation, payload));
        }
    }

    private void handleYahooFetchResult(long generation, String payload) {
        fetchInProgress = false;
        if (!isActiveGeneration(generation)) {
            return;
        }

        List<MarketQuote> quotes = new ArrayList<>();
        List<String> failedMarkets = new ArrayList<>();
        List<MarketStatus> diagnostics = new ArrayList<>();
        long triggeredCooldownUntil = 0L;

        try {
            JSONArray results = new JSONArray(payload);
            for (int index = 0; index < results.length(); index++) {
                JSONObject item = results.optJSONObject(index);
                if (item == null) {
                    continue;
                }

                String marketId = item.optString("id", "");
                boolean ok = item.optBoolean("ok", false);
                if (ok) {
                    double price = item.optDouble("price", Double.NaN);
                    long timestamp = item.optLong("timestamp", -1L);
                    if (Double.isFinite(price) && price > 0 && timestamp > 0) {
                        MarketQuote quote = new MarketQuote(marketId, price, timestamp);
                        quotes.add(quote);
                        diagnostics.add(new MarketStatus(
                                marketId, true, price, timestamp, null
                        ));
                        continue;
                    }
                }

                String reason = item.optString("reason", "原因不明");
                failedMarkets.add(marketId);
                diagnostics.add(new MarketStatus(marketId, false, 0, 0, reason));
                if (item.optBoolean("rateLimited", false)) {
                    triggeredCooldownUntil =
                            System.currentTimeMillis() + RATE_LIMIT_COOLDOWN_MS;
                    setRateLimitCooldownUntil(triggeredCooldownUntil);
                }
            }
        } catch (JSONException exception) {
            failedMarkets = new ArrayList<>(MARKET_SYMBOLS.keySet());
            diagnostics.clear();
            for (String marketId : MARKET_SYMBOLS.keySet()) {
                diagnostics.add(new MarketStatus(
                        marketId,
                        false,
                        0,
                        0,
                        "JS result parse error"
                ));
            }
        }

        for (MarketQuote quote : quotes) {
            latestQuotes.put(quote.marketId, quote);
        }
        if (!latestQuotes.isEmpty()) {
            applyLatestQuotes();
        }
        lastAttempted = true;
        lastSuccessCount = quotes.size();
        lastFailedMarkets = failedMarkets;
        lastDiagnostics = diagnostics;
        lastUpdatedAtMillis = System.currentTimeMillis();
        lastCooldownUntilMillis = triggeredCooldownUntil;
        reportCurrentStatus(false);
    }

    private long getRateLimitCooldownUntil() {
        return getSharedPreferences(PREFS_NAME, MODE_PRIVATE)
                .getLong(PREF_COOLDOWN_UNTIL, 0L);
    }

    private void setRateLimitCooldownUntil(long cooldownUntil) {
        SharedPreferences preferences = getSharedPreferences(PREFS_NAME, MODE_PRIVATE);
        preferences.edit().putLong(PREF_COOLDOWN_UNTIL, cooldownUntil).apply();
    }

    private void reportCooldownStatus(long cooldownUntil) {
        lastAttempted = true;
        lastSuccessCount = 0;
        lastFailedMarkets = new ArrayList<>(MARKET_SYMBOLS.keySet());
        lastDiagnostics = new ArrayList<>();
        for (String marketId : MARKET_SYMBOLS.keySet()) {
            lastDiagnostics.add(new MarketStatus(
                    marketId,
                    false,
                    0,
                    0,
                    "HTTP 429 cooldown中（未取得）"
            ));
        }
        lastCooldownUntilMillis = cooldownUntil;
        reportCurrentStatus(false);
    }

    private void applyLatestQuotes() {
        if (webView == null || latestQuotes.isEmpty()) {
            return;
        }
        JSONArray updates = new JSONArray();
        for (MarketQuote quote : latestQuotes.values()) {
            JSONObject update = new JSONObject();
            try {
                update.put("id", quote.marketId);
                update.put("current", quote.price);
                update.put("timestamp", quote.timestamp);
                updates.put(update);
            } catch (JSONException ignored) {
                return;
            }
        }
        webView.evaluateJavascript("window.updateCurrentValues(" + updates + ");", null);
    }

    private void reportCurrentStatus(boolean manualUpdating) {
        if (webView == null) {
            return;
        }
        JSONObject status = new JSONObject();
        try {
            status.put("attempted", lastAttempted);
            status.put("total", MARKET_SYMBOLS.size());
            status.put("successCount", lastSuccessCount);
            status.put("manualUpdating", manualUpdating);
            status.put(
                    "lastUpdatedAt",
                    lastUpdatedAtMillis > 0 ? lastUpdatedAtMillis : JSONObject.NULL
            );
            JSONArray failed = new JSONArray();
            for (String marketId : lastFailedMarkets) {
                failed.put(marketId);
            }
            status.put("failedMarkets", failed);
            JSONArray quotes = new JSONArray();
            for (MarketStatus diagnostic : lastDiagnostics) {
                JSONObject item = new JSONObject();
                item.put("id", diagnostic.marketId);
                item.put("ok", diagnostic.ok);
                item.put("price", diagnostic.ok ? diagnostic.price : JSONObject.NULL);
                item.put("timestamp", diagnostic.ok ? diagnostic.timestamp : JSONObject.NULL);
                item.put("reason", diagnostic.reason != null ? diagnostic.reason : JSONObject.NULL);
                quotes.put(item);
            }
            status.put("quotes", quotes);
            long cooldownUntil = Math.max(lastCooldownUntilMillis, getRateLimitCooldownUntil());
            boolean cooldownActive = cooldownUntil > System.currentTimeMillis();
            status.put("cooldownActive", cooldownActive);
            status.put("cooldownUntil", cooldownActive ? cooldownUntil : JSONObject.NULL);
        } catch (JSONException ignored) {
            return;
        }
        webView.evaluateJavascript("window.updateCurrentStatus(" + status + ");", null);
    }

    private static final class MarketQuote {
        private final String marketId;
        private final double price;
        private final long timestamp;

        private MarketQuote(String marketId, double price, long timestamp) {
            this.marketId = marketId;
            this.price = price;
            this.timestamp = timestamp;
        }
    }

    private static final class MarketStatus {
        private final String marketId;
        private final boolean ok;
        private final double price;
        private final long timestamp;
        private final String reason;

        private MarketStatus(String marketId, boolean ok, double price, long timestamp, String reason) {
            this.marketId = marketId;
            this.ok = ok;
            this.price = price;
            this.timestamp = timestamp;
            this.reason = reason;
        }
    }

    private boolean handleUrl(String url) {
        Uri uri = Uri.parse(url);
        String host = uri.getHost();
        String path = uri.getPath();

        boolean internal =
                "https".equals(uri.getScheme())
                && "xiaqui.github.io".equals(host)
                && path != null
                && (path.equals("/market-weather") || path.startsWith("/market-weather/"));

        if (internal) {
            return false;
        }

        String scheme = uri.getScheme();
        if (!"http".equals(scheme) && !"https".equals(scheme)) {
            return true;
        }

        try {
            startActivity(new Intent(Intent.ACTION_VIEW, uri));
        } catch (Exception ignored) {
        }
        return true;
    }

    private void showError(String title, String detail) {
        String html = "<!doctype html><html><head><meta charset='utf-8'>"
                + "<meta name='viewport' content='width=device-width,initial-scale=1'>"
                + "<style>body{font-family:sans-serif;padding:24px;line-height:1.5;}"
                + "h2{font-size:20px;}pre{white-space:pre-wrap;word-break:break-word;"
                + "background:#eee;padding:12px;}</style>"
                + "</head><body><h2>" + escapeHtml(title) + "</h2><pre>"
                + escapeHtml(detail) + "</pre>"
                + "<p>Android System WebView: "
                + escapeHtml(webView.getSettings().getUserAgentString())
                + "</p></body></html>";
        webView.loadDataWithBaseURL(null, html, "text/html", "UTF-8", null);
    }

    private String escapeHtml(String text) {
        if (text == null) {
            return "";
        }
        return text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\"", "&quot;")
                .replace("'", "&#39;");
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        if (webView != null) {
            webView.saveState(outState);
        }
        super.onSaveInstanceState(outState);
    }

    @Override
    protected void onDestroy() {
        polling = false;
        pollingGeneration++;
        if (fetchWebView != null) {
            fetchWebView.removeJavascriptInterface("AndroidYahoo");
            fetchWebView.destroy();
        }
        if (webView != null) {
            webView.destroy();
        }
        super.onDestroy();
    }
}
