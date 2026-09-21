# market-weather

日経平均、NYダウ、ドル円、金価格を「天気予報」のように表示するAndroidアプリの実験プロジェクトです。

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
4市場の過去1年の日足を取得し、正本である `shared/forecast.json` の現在値と予測値を
更新します。続けて
`python scripts/sync_forecast.py` を実行すると Android / Web の配布用JSONへ反映されます。

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
バックテストの方向正解率とサンプル数も市場別に表示します。これは最初のbaselineであり、
将来の高い予測精度を示すものではありません。

Android APKに加えて、同じ予報データを表示するWeb版をGitHub Pagesで公開し、iOS / Windows / Androidブラウザからも確認できる構成を目指します。

## ドキュメント

- [開発仕様](docs/market-weather-spec.md)
- [TODO / 開発・検証タスク](docs/TODO.md)

## 初期技術構成

- Kotlin
- Jetpack Compose
- Material 3
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
