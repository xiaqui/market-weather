package jp.xiaqui.marketweather;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
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

public class MainActivity extends Activity {
    private static final String START_URL = "https://xiaqui.github.io/market-weather/";
    private static final String YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/";
    private static final long UPDATE_INTERVAL_MS = 60_000L;
    private static final int NETWORK_TIMEOUT_MS = 10_000;
    private static final Map<String, String> MARKET_SYMBOLS = createMarketSymbols();

    private WebView webView;
    private final Handler updateHandler = new Handler(Looper.getMainLooper());
    private final ExecutorService networkExecutor = Executors.newSingleThreadExecutor();
    private final Map<String, MarketQuote> latestQuotes = new LinkedHashMap<>();
    private boolean polling;
    private long pollingGeneration;
    private Runnable scheduledUpdate;

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

        if (savedInstanceState == null) {
            webView.loadUrl(START_URL);
        } else {
            webView.restoreState(savedInstanceState);
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        polling = true;
        pollingGeneration++;
        schedulePolling(pollingGeneration, 0);
    }

    @Override
    protected void onPause() {
        polling = false;
        pollingGeneration++;
        cancelScheduledPolling();
        super.onPause();
    }

    private void schedulePolling(long generation, long delayMs) {
        cancelScheduledPolling();
        scheduledUpdate = () -> fetchCurrentValues(generation);
        updateHandler.postDelayed(scheduledUpdate, delayMs);
    }

    private void cancelScheduledPolling() {
        if (scheduledUpdate != null) {
            updateHandler.removeCallbacks(scheduledUpdate);
            scheduledUpdate = null;
        }
    }

    private boolean isActiveGeneration(long generation) {
        return polling && generation == pollingGeneration;
    }

    private void fetchCurrentValues(long generation) {
        if (!isActiveGeneration(generation)) {
            return;
        }
        networkExecutor.execute(() -> {
            List<MarketQuote> quotes = new ArrayList<>();
            for (Map.Entry<String, String> market : MARKET_SYMBOLS.entrySet()) {
                try {
                    MarketQuote quote = fetchMarketQuote(market.getKey(), market.getValue());
                    if (quote != null) {
                        quotes.add(quote);
                    }
                } catch (IOException | JSONException ignored) {
                    // Keep the last successfully displayed value and retry on the next interval.
                }
            }
            runOnUiThread(() -> {
                if (!isActiveGeneration(generation)) {
                    return;
                }
                for (MarketQuote quote : quotes) {
                    latestQuotes.put(quote.marketId, quote);
                }
                if (!latestQuotes.isEmpty()) {
                    applyLatestQuotes();
                }
                schedulePolling(generation, UPDATE_INTERVAL_MS);
            });
        });
    }

    private MarketQuote fetchMarketQuote(String marketId, String symbol)
            throws IOException, JSONException {
        String encodedSymbol = URLEncoder.encode(symbol, StandardCharsets.UTF_8.name());
        HttpURLConnection connection = (HttpURLConnection) new URL(
                YAHOO_CHART_URL + encodedSymbol
        ).openConnection();
        connection.setConnectTimeout(NETWORK_TIMEOUT_MS);
        connection.setReadTimeout(NETWORK_TIMEOUT_MS);
        connection.setRequestMethod("GET");
        connection.setRequestProperty("Accept", "application/json");

        try {
            if (connection.getResponseCode() != HttpURLConnection.HTTP_OK) {
                return null;
            }
            String response = readResponse(connection);
            JSONObject chart = new JSONObject(response).optJSONObject("chart");
            JSONArray results = chart == null ? null : chart.optJSONArray("result");
            JSONObject result = results == null ? null : results.optJSONObject(0);
            JSONObject meta = result == null ? null : result.optJSONObject("meta");
            if (meta == null) {
                return null;
            }
            double price = meta.optDouble("regularMarketPrice", Double.NaN);
            long timestamp = meta.optLong("regularMarketTime", -1L);
            if (!Double.isFinite(price) || price <= 0 || timestamp < 0) {
                return null;
            }
            return new MarketQuote(marketId, price, timestamp);
        } finally {
            connection.disconnect();
        }
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
        cancelScheduledPolling();
        networkExecutor.shutdownNow();
        if (webView != null) {
            webView.destroy();
        }
        super.onDestroy();
    }
}
