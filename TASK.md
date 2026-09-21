# TASK.md

## 目的

Market Weather の本番Android APKを、現在のComposeネイティブ画面から
GitHub Pages版を表示する軽量WebViewカプセルへ切り替える。

実装は既存 `eiken2-webview` の実績済みMainActivity相当をTASK内に直接記載し、それを使用する。

Web版を表示の正本とし、Android APKは原則としてそのWeb版を包むだけの薄い殻にする。
現行Compose版は削除して失わせず、保全して今後たまにWeb版へ追従できる状態を残す。

## 現状

- Web版は GitHub Pages で公開済み:
  `https://xiaqui.github.io/market-weather/`
- Web版は4市場の実現在値・実計算baseline予報を表示している。
- 現在のAndroid APKはJetpack Composeで画面を別実装し、
  APK内のforecast.jsonを読むネイティブ版。
- そのためWebとAndroidでUI/データを二重管理している。
- `xiaqui/eiken2-webview` には、WebViewラッパーとして実績のある構成がある。

## 今回の方針

### 1. 現行Compose版を保全

WebView化前の現在の main を、今後参照・保守できる形で保全する。

推奨:
- `native-compose` branch を現在の main から作成してpushする

または同等に明確で安全な方法で保全してよい。

目的は、WebView化後もCompose版を失わず、
必要な節目でWeb版に合わせて保守できるようにすること。

この保全branchでは通常開発を進めない。

### 2. Android本番版をWebViewカプセルへ変更

Codex Cloud から `xiaqui/eiken2-webview` を参照できることは前提にしない。
参照repoをcloneしたり読みに行ったりせず、下記の実績済み `eiken2-webview` の
`MainActivity.java` 相当を Market Weather 用へほぼそのまま移植する。

変更点は主に以下だけでよい。

- package: `jp.xiaqui.marketweather`
- START_URL: `https://xiaqui.github.io/market-weather/`
- 内部URL判定: hostが `xiaqui.github.io` かつ path が `/market-weather/` 配下
- applicationId: 既存の `jp.xiaqui.marketweather` を維持
- アプリ名: `Market Weather`

実績済みベースコード:

```java
package jp.xiaqui.marketweather;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.webkit.CookieManager;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

public class MainActivity extends Activity {
    private static final String START_URL = "https://xiaqui.github.io/market-weather/";
    private WebView webView;

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
            public void onReceivedError(
                    WebView view,
                    int errorCode,
                    String description,
                    String failingUrl
            ) {
                super.onReceivedError(view, errorCode, description, failingUrl);
                showError(
                        "WebView load error",
                        "code=" + errorCode + "\n" + description + "\n\n" + failingUrl
                );
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
        });

        if (savedInstanceState == null) {
            webView.loadUrl(START_URL);
        } else {
            webView.restoreState(savedInstanceState);
        }
    }

    private boolean handleUrl(String url) {
        Uri uri = Uri.parse(url);
        String host = uri.getHost();
        String path = uri.getPath();

        boolean internal =
                "xiaqui.github.io".equals(host)
                && path != null
                && (path.equals("/market-weather") || path.startsWith("/market-weather/"));

        if (internal) {
            return false;
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
        if (webView != null) {
            webView.destroy();
        }
        super.onDestroy();
    }
}
```

このコードを基準にし、必要最小限の変更だけ行うこと。
「より高機能にする」ための独自機能追加は今回しない。

Manifestも `eiken2-webview` 相当の単純構成でよい。

```xml
<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <uses-permission android:name="android.permission.INTERNET" />
    <application
        android:allowBackup="true"
        android:label="Market Weather"
        android:theme="@android:style/Theme.Material.Light.NoActionBar"
        android:usesCleartextTraffic="false">
        <activity
            android:name=".MainActivity"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
    </application>
</manifest>
```

既存インストールから更新可能な形を優先する。

### 3. WebView基本仕様

最低限、以下を実装する。

- JavaScript 有効
- DOM Storage 有効
- HTTPSのみを前提にする
- cleartext traffic は許可しない
- INTERNET permission のみ必要最小限で付与
- WebView内の戻る履歴がある場合は戻る操作で前ページへ戻る
- Activity再生成時にWebView stateを保存・復元
- メインフレームのロード失敗時は簡潔なエラー画面を表示
- Android System WebViewの通常機能を使い、独自ブラウザエンジンは持たない
- 不要なJavaScript bridgeは作らない
- ファイルアクセス等、不要な権限・危険なWebView設定は追加しない

### 4. URLハンドリング

Market Weather本体はWebView内で開く。

内部扱い:

```text
https://xiaqui.github.io/market-weather/
```

およびその配下。

それ以外のHTTP/HTTPSリンクは外部ブラウザへ渡す。

`intent:` や特殊スキームを安易にWebView内で実行しない。
必要な場合だけ安全に外部Intentへ渡す。

### 5. Androidバージョン

Android 6 / Z3TC対応は今回の必須条件ではない。

`eiken2-webview` は minSdk 23 だが、
Market Weatherでは以下の優先順位とする。

1. WebView化を簡潔・安定して完了する
2. 既存Android環境・Actionsを壊さない
3. そのうえで追加の手間がほぼ無ければ minSdk 23 に下げてもよい

minSdk 23対応のために追加の分岐・大きな互換コード・不安定化が必要なら、
無理に対応せず既存 minSdk 26 のままでよい。

Z3TCでWebページが白画面になった過去実績があるため、
「APKがAndroid 6へインストールできること」自体を今回の完成条件にしない。

### 6. Compose版固有依存の整理

本番WebView APKで不要になるものは削除・簡素化する。

候補:
- Jetpack Compose関連依存
- Material3関連依存
- Gson
- APK内 forecast.json
- Android側 forecast JSON unit test
- Android build前の `sync_forecast.py` 依存

ただしWeb版・Python予測系で必要な

- `shared/forecast.json`
- `web/forecast.json`
- `scripts/sync_forecast.py`

は残す。

Android APKのためだけにforecast.jsonをコピーする必要はなくす。

### 7. Web版とAPKの責務を分離

今後の原則をREADMEまたはdocsへ記載する。

- Web版 / GitHub Pages が表示の正本
- 通常の市場データ・予測・UI更新ではAPK再build不要
- APK再buildが必要なのは、URL、WebView設定、権限、アプリアイコン等の殻を変更した時
- Composeネイティブ版は保全版として、節目で必要に応じて追従する

### 8. GitHub Actions

既存の `Build Android APK` をWebView版に合わせて整理する。

要件:
- push / workflow_dispatch でbuild可能
- Android unit testが存在するなら実行
- debug APKを生成
- Artifact名 `market-weather-debug` は維持
- 出力ファイル名 `market-weather-debug.apk` も維持
- Compose版用のforecast同期処理が不要なら外す
- Cloud内にAndroid SDKが無くても、GitHub Actionsを正式build確認とする

### 9. テスト / 確認

最低限以下を確認する。

- Python既存テストを壊していない
- `git diff --check`
- Android build
- WebViewの開始URLがMarket Weather Pagesになっている
- applicationIdが `jp.xiaqui.marketweather` のまま
- INTERNET以外に不要な権限が増えていない
- 内部URL判定がMarket Weather Pages配下に限定されている
- 外部HTTP/HTTPS URLが外部ブラウザへ渡る
- APK内forecast.jsonに依存しなくなっている

## UI

Webページ自体のデザイン・予測ロジックは今回変更しない。

APKは公開中のWeb版をそのまま表示すること。

## GitHub運用

- mainへ直接pushしない
- 現行Compose版を先に保全する
- WebView化は専用branchで実装
- commit / push
- Pull Requestを作成
- GitHub ActionsでAPK build成功を確認
- mergeは行わない

## 完了条件

- 現行Compose版が参照可能な形で保全されている
- Android本番実装がWebViewカプセルになっている
- Market Weather Pagesを表示する
- 外部リンクは外部ブラウザへ渡る
- APK内forecast.jsonへの依存がなくなっている
- applicationIdを維持
- Python既存テスト成功
- Android build成功
- `git diff --check` 成功
- PR作成済み

## 最後の報告

以下だけ報告する。

- Compose版の保全方法 / branch名
- WebView化branch名
- commit SHA
- PR番号
- minSdkを23にしたか26維持か、その理由
- test/build結果
- 変更ファイル
- 残課題
