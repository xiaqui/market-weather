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

## 仕様

詳細は [docs/market-weather-spec.md](docs/market-weather-spec.md) を参照してください。

## 初期技術構成

- Kotlin
- Jetpack Compose
- Material 3
- Python
- GitHub Actions
- Gradle Wrapper

## 初期対象

- 日経平均
- NYダウ
- USD/JPY
- GOLD

## 注意

本プロジェクトは統計的予測の検証を目的とした実験です。将来の価格や利益を保証するものではありません。
