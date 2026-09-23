package jp.xiaqui.marketweather;

import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Bundle;
import android.view.MotionEvent;
import android.webkit.CookieManager;
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

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.ConnectException;
import java.net.SocketTimeoutException;
import java.net.UnknownHostException;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import javax.net.ssl.SSLException;

public class MainActivity extends Activity {
    private static final String START_URL = "https://xiaqui.github.io/market-weather/";
    private static final String YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/";
    private static final String UA_APP_SUFFIX = " MarketWeatherApp/1.0";
    private static final long MARKET_REQUEST_SPACING_MS = 1_500L;
    private static final long RATE_LIMIT_COOLDOWN_MS = 5 * 60_000L;
    private static final String PREFS_NAME = "market_weather_current";
    private static final String PREF_COOLDOWN_UNTIL = "yahoo_cooldown_until";
    private static final int NETWORK_TIMEOUT_MS = 10_000;
    private static final float PULL_REFRESH_THRESHOLD_DP = 96f;
    private static final Map<String, String> MARKET_SYMBOLS = createMarketSymbols();

    private WebView webView;
    private final ExecutorService networkExecutor = Executors.newSingleThreadExecutor();
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

        fetchInProgress = true;
        networkExecutor.execute(() -> {
            List<MarketQuote> quotes = new ArrayList<>();
            List<String> failedMarkets = new ArrayList<>();
            List<MarketStatus> diagnostics = new ArrayList<>();
            List<Map.Entry<String, String>> marketsToFetch =
                    new ArrayList<>(MARKET_SYMBOLS.entrySet());
            long triggeredCooldownUntil = 0L;

            for (int index = 0; index < marketsToFetch.size(); index++) {
                if (index > 0) {
                    try {
                        Thread.sleep(MARKET_REQUEST_SPACING_MS);
                    } catch (InterruptedException exception) {
                        Thread.currentThread().interrupt();
                        break;
                    }
                }

                Map.Entry<String, String> market = marketsToFetch.get(index);
                String marketId = market.getKey();
                MarketFetchResult result = fetchMarketQuote(marketId, market.getValue());
                diagnostics.add(result.status);
                if (result.quote != null) {
                    quotes.add(result.quote);
                } else {
                    failedMarkets.add(marketId);
                }

                if (result.rateLimited) {
                    triggeredCooldownUntil = System.currentTimeMillis() + RATE_LIMIT_COOLDOWN_MS;
                    setRateLimitCooldownUntil(triggeredCooldownUntil);
                    for (int skippedIndex = index + 1;
                            skippedIndex < marketsToFetch.size();
                            skippedIndex++) {
                        String skippedMarketId = marketsToFetch.get(skippedIndex).getKey();
                        failedMarkets.add(skippedMarketId);
                        diagnostics.add(new MarketStatus(
                                skippedMarketId,
                                false,
                                0,
                                0,
                                "HTTP 429 cooldown中（未取得）"
                        ));
                    }
                    break;
                }
            }

            long finalCooldownUntil = triggeredCooldownUntil;
            runOnUiThread(() -> {
                fetchInProgress = false;
                if (!isActiveGeneration(generation)) {
                    return;
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
                lastCooldownUntilMillis = finalCooldownUntil;
                reportCurrentStatus(false);
            });
        });
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

    private MarketFetchResult fetchMarketQuote(String marketId, String symbol) {
        String encodedSymbol = URLEncoder.encode(symbol, StandardCharsets.UTF_8);
        HttpURLConnection connection = null;

        try {
            connection = (HttpURLConnection) new URL(
                    YAHOO_CHART_URL + encodedSymbol
            ).openConnection();
            connection.setConnectTimeout(NETWORK_TIMEOUT_MS);
            connection.setReadTimeout(NETWORK_TIMEOUT_MS);
            connection.setRequestMethod("GET");
            connection.setRequestProperty("Accept", "application/json");
            int statusCode = connection.getResponseCode();
            if (statusCode != HttpURLConnection.HTTP_OK) {
                return MarketFetchResult.failure(
                        marketId,
                        "HTTP " + statusCode,
                        statusCode == 429
                );
            }
            String response = readResponse(connection);
            return parseMarketQuote(marketId, response);
        } catch (UnknownHostException exception) {
            return MarketFetchResult.failure(marketId, formatException(exception));
        } catch (SocketTimeoutException exception) {
            return MarketFetchResult.failure(marketId, formatException(exception));
        } catch (ConnectException exception) {
            return MarketFetchResult.failure(marketId, formatException(exception));
        } catch (SSLException exception) {
            return MarketFetchResult.failure(marketId, formatException(exception));
        } catch (JSONException exception) {
            return MarketFetchResult.failure(
                    marketId,
                    "JSON parse error: " + formatException(exception)
            );
        } catch (IOException exception) {
            return MarketFetchResult.failure(marketId, formatException(exception));
        } finally {
            if (connection != null) {
                connection.disconnect();
            }
        }
    }

    private MarketFetchResult parseMarketQuote(String marketId, String response) throws JSONException {
        JSONObject chart = new JSONObject(response).optJSONObject("chart");
        JSONArray results = chart == null ? null : chart.optJSONArray("result");
        if (results == null || results.length() == 0 || results.optJSONObject(0) == null) {
            return MarketFetchResult.failure(marketId, "chart.result missing");
        }
        JSONObject meta = results.optJSONObject(0).optJSONObject("meta");
        if (meta == null) {
            return MarketFetchResult.failure(marketId, "meta missing");
        }
        Object rawPrice = meta.opt("regularMarketPrice");
        if (!(rawPrice instanceof Number)) {
            return MarketFetchResult.failure(marketId, "regularMarketPrice missing or invalid");
        }
        double price = ((Number) rawPrice).doubleValue();
        if (!Double.isFinite(price) || price <= 0) {
            return MarketFetchResult.failure(marketId, "regularMarketPrice missing or invalid");
        }
        Object rawTimestamp = meta.opt("regularMarketTime");
        if (!(rawTimestamp instanceof Number)) {
            return MarketFetchResult.failure(marketId, "regularMarketTime missing or invalid");
        }
        long timestamp = ((Number) rawTimestamp).longValue();
        if (timestamp <= 0) {
            return MarketFetchResult.failure(marketId, "regularMarketTime missing or invalid");
        }
        return MarketFetchResult.success(new MarketQuote(marketId, price, timestamp));
    }

    private String formatException(Exception exception) {
        String name = exception.getClass().getSimpleName();
        String message = exception.getMessage();
        if (message == null || message.trim().isEmpty()) {
            return name;
        }
        String singleLine = message.replace('\r', ' ').replace('\n', ' ').trim();
        if (singleLine.length() > 120) {
            singleLine = singleLine.substring(0, 117) + "...";
        }
        return name + ": " + singleLine;
    }

    private String readResponse(HttpURLConnection connection) throws IOException {
        StringBuilder response = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(
                connection.getInputStream(), StandardCharsets.UTF_8
        ))) {
            char[] buffer = new char[4096];
            int count;
            while ((count = reader.read(buffer)) != -1) {
                response.append(buffer, 0, count);
            }
        }
        return response.toString();
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

    private static final class MarketFetchResult {
        private final MarketQuote quote;
        private final MarketStatus status;
        private final boolean rateLimited;

        private MarketFetchResult(MarketQuote quote, MarketStatus status, boolean rateLimited) {
            this.quote = quote;
            this.status = status;
            this.rateLimited = rateLimited;
        }

        private static MarketFetchResult success(MarketQuote quote) {
            return new MarketFetchResult(
                    quote,
                    new MarketStatus(quote.marketId, true, quote.price, quote.timestamp, null),
                    false
            );
        }

        private static MarketFetchResult failure(String marketId, String reason) {
            return failure(marketId, reason, false);
        }

        private static MarketFetchResult failure(
                String marketId,
                String reason,
                boolean rateLimited
        ) {
            return new MarketFetchResult(
                    null,
                    new MarketStatus(marketId, false, 0, 0, reason),
                    rateLimited
            );
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
        networkExecutor.shutdownNow();
        if (webView != null) {
            webView.destroy();
        }
        super.onDestroy();
    }
}
