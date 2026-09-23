# market-weather

日経平均、NYダウ、ドル円、金価格を「天気予報」のように表示するWebアプリとAndroidアプリの実験プロジェクトです。

一点の終値を当てにいくのではなく、翌営業日の

- 上昇／下落確率
- 予想レンジ
- 予報信頼度
- 市場の荒れやすさ

を表示することを目的とします。

## 開発方針

まずは固定JSONを読み込むAndroidアプリを完成させ、GitHub ActionsからDebug APKを生成できる状態を作ります。

その後、Pythonによる市場データ取得、特徴量生成、予測、バックテストを段階的に追加します。

`python scripts/fetch_market_data.py` は Yahoo Finance のキー不要な Chart API から
4市場の過去10年の日足を取得し、正本である `shared/forecast.json` の現在値と予測値を
更新します。続けて
`python scripts/sync_forecast.py` を実行するとAndroid / Webの配布用JSONへ反映されます。
Android側にも互換用コピーは生成されますが、WebView版の表示やビルドはその内容に依存しません。

## Web版とAndroid APK

GitHub Pagesで公開するWeb版が表示の正本です。Android APKは
`https://xiaqui.github.io/market-weather/` をAndroid System WebViewで表示する薄いカプセルであり、
通常の市場データ・予測・Web UIの更新ではAPKの再ビルドを必要としません。

APKの再ビルドが必要なのは、表示URL、WebView設定、権限、アプリアイコンなどAndroid側の
殻を変更した場合です。従来のComposeネイティブ版は`native-compose`ブランチに保全し、
必要な節目でWeb版への追従を検討します。

GitHub Actions では Debug APK を artifact `market-weather-debug` として生成します。
取得する場合は GitHub の `Actions` → `Build Android APK` → 成功した workflow run →
`Artifacts` → `market-weather-debug` の順に開いてダウンロードしてください。

### Android APK の固定署名

GitHub Actions で毎回同じ署名鍵を使う場合は、Repository Secrets に次の4項目を登録します。

- `KEYSTORE_BASE64`: keystore ファイル全体をBase64化した文字列
- `KEYSTORE_PASSWORD`: keystore のパスワード
- `KEY_ALIAS`: 署名鍵のalias
- `KEY_PASSWORD`: 署名鍵のパスワード

4項目がそろっているbuildでは、workflowが一時keystoreを復元し、Debug APKを固定鍵で署名します。
Secretsが未設定のbuildは従来どおりrunnerのdebug署名へフォールバックします。
Secretsを追加・更新した後は、新しいworkflow runを開始して固定署名APKを生成してください。

固定署名へ切り替える最初の1回だけは、既に端末へ入っている従来署名版をアンインストールしてから
インストールする必要があります。その後は同じ `applicationId` と固定署名鍵を維持する限り、
新しいAPKをアンインストールせず上書きインストールできます。keystoreを紛失・変更すると
その署名系列では上書き更新できなくなるため、鍵は安全に保管してください。

### Trend baseline

初期予測は学習モデルではなく、説明可能なTrend baselineです。1・5・20日騰落率と
5・20日移動平均乖離を、5・20日の日次ボラティリティで標準化して加重します。
重みは順に `0.10 / 0.20 / 0.25 / 0.15 / 0.30`、個々の標準化シグナルは
`-3〜3` に制限し、`0.5 + 0.32 × tanh(合成シグナル)` で上昇確率へ変換します。
このため確率が過度に0または1へ張り付きません。

予想レンジは現在値に20日ボラティリティ（最低0.2%）の1.28倍を上下へ適用します。
信頼度は5方向シグナルの一致度とデータ量（60営業日で十分）から算出します。
天気は上昇確率（62%以上: sunny、54%以上: partly_cloudy、46%超: cloudy、
それ以下: rainy）、リスクは日次20日ボラティリティ（0.8%未満: calm、1.5%未満:
normal、2.5%未満: caution、それ以上: storm）から決定論的に決めます。

同じコマンドは、各時点までのデータだけで翌営業日の方向を予測するwalk-forward
バックテストで、Trend、4市場の金融天気図による過去類似局面、両者の50/50 Ensembleの
方向正解率とサンプル数も市場別に表示します。これは検証可能な初期モデルであり、
将来の高い予測精度を示すものではありません。

非重複期間で再現性を確認するフェーズ2レポートは
`python scripts/validate_phase2.py`で`reports/phase2-validation.json`へ生成できます。
最新252セッションはDiscovery、それ以前の最大4区間はValidationとして明確に分離されます。

Android APKに加えて、同じ予報データを表示するWeb版をGitHub Pagesで公開し、iOS / Windows / Androidブラウザからも確認できる構成を目指します。

## ドキュメント

- [開発仕様](docs/market-weather-spec.md)
- [TODO / 開発・検証タスク](docs/TODO.md)
- [予報画面の見方 / 各予報値の説明](docs/forecast-values-guide.md)
- [引き継ぎ書](docs/HANDOFF.md)
- [開発環境・端末検証バックログ](docs/development-environment.md)

## 技術構成

- Android System WebView
- Python
- GitHub Actions
- Gradle Wrapper
- GitHub Pages

## 初期対象

- 日経平均
- NYダウ
- USD/JPY
- GOLD

## 注意

本プロジェクトは統計的予測の検証を目的とした実験です。将来の価格や利益を保証するものではありません。
