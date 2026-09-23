# Market Weather 引き継ぎ書

最終更新: 2026-09-23

## 1. プロジェクト概要

Market Weather は、日経平均 / NYダウ / USDJPY / GOLD の4市場について、
次営業日の方向・値幅・荒れやすさを「金融天気予報」として見せる実験プロジェクト。

表示の正本は GitHub Pages。

- Web: https://xiaqui.github.io/market-weather/
- Android: 上記Pagesを表示するWebViewカプセル
- applicationId: `jp.xiaqui.marketweather`
- minSdk: 26

Androidの現在値だけは、Pagesの予報JSONとは別にYahoo Financeから取得して画面へ上書きする。
現在値が更新されても、天気 / 上昇確率 / 予想レンジ / confidence / Trend / Analog は変えない。

## 2. 現在の予報ロジック

予報入力は確定済み日足のみ。形成中の日足を予測へ混ぜない。

本番の最終上昇確率は次の50:50 Ensemble。

```text
up_probability
= 0.5 × trend_probability
+ 0.5 × analog_probability
```

Analog候補が15件未満ならTrendへフォールバック。

### Trend
対象市場自身の直近トレンドを使用。

- 1日騰落率
- 5日騰落率
- 20日騰落率
- 5日移動平均乖離
- 20日移動平均乖離
- 5 / 20日ボラティリティで正規化

### Analog
Cross-Asset Historical Analog「金融天気図」。

4市場をまとめた30次元状態を作り、過去約10年から類似局面を最大30件検索する。
対象市場の休場時間と、その間の他市場累積変動も特徴に含める。

詳細は `docs/forecast-values-guide.md` と `docs/forecast-algorithm.md` を参照。

## 3. 画面仕様

カードは意図的に情報量を絞る。

- 現在値
- 予想レンジ
- 天気マーク
- 上昇確率

confidence、risk、Trend、Analog、元データ最終日、予測対象セッション等は詳細ダイアログへ置く。

見出しは次の形式。

```text
次営業日の金融天気予報　9月23日 7:30発表
```

発表時刻は forecast JSON の `generated_at` を日本時間で表示する。

Androidでは市場名の横に、予報生成時の基準値に対する現在値の位置を表示する。

```text
↑ 1.24%
ー 0.05%
↓ 0.83%
```

判定のdeadbandは ±0.1%。

- +0.1%超: ↑
- ±0.1%以内: ー
- -0.1%未満: ↓

これは予報方向ではなく、予報時点の基準値に対する現在値の途中経過。

## 4. Android現在値取得

Android側は、表示用WebViewとは別の非表示ローカルWebViewを使う。

ローカルasset:

```text
android/app/src/main/assets/yahoo_fetch.html
```

JavaScript `fetch()` で Yahoo Finance Chart API を叩き、Java bridgeで `MainActivity` へ返す。
AP37で実績があった方式を採用した結果、HttpURLConnection方式より実機で安定した。

対象:

```text
^N225
^DJI
JPY=X
GC=F
```

挙動:

- 起動 / フォアグラウンド復帰で取得
- 下スワイプで手動更新
- 60秒pollは廃止
- 4市場は1.5秒間隔
- HTTP 429時は5分cooldown
- 一部成功は保持
- 成功した現在値はSharedPreferencesへ保存
- 画面回転では不要な再取得をしない
- 診断ログは通常画面では非表示

## 5. APK固定署名

GitHub Actions `Build Android APK` は固定署名に対応済み。

Repository Secrets:

```text
KEYSTORE_BASE64
KEYSTORE_PASSWORD
KEY_ALIAS
KEY_PASSWORD
```

keystore本体やパスワードはrepoへ入れない。

固定署名へ切り替え後、実機で

1. 旧ランダムdebug署名版を一度アンインストール
2. 固定署名版をインストール
3. 次の固定署名APKをアンインストールなしで上書き

まで確認済み。

現在の `versionCode` は 2。

## 6. APK配布

GitHub Actions artifact名:

```text
market-weather-debug
```

Drive側も同じAPKを固定ファイルへ上書きして運用。

Drive file ID:

```text
16l-OTKL2-RNjSyPy0wyXm4Mfeqd7Z12y
```

ファイル名:

```text
market-weather-debug.apk
```

APK生成後は、成功run / head SHA / artifactを確認してからDriveの同一ファイルを上書きする。

ZIPをDriveへ置かず、artifact ZIPから実APKを取り出して上書きすること。

## 7. 日次予報更新

workflow:

```text
Update Daily Forecast
```

平日 22:30 UTC、JSTでは翌朝7:30頃。

処理:

1. Yahoo Financeからデータ取得
2. 形成中足を除外
3. 予報生成
4. `shared/forecast.json` 更新
5. `web/forecast.json` へ同期
6. 差分がある場合だけmainへcommit
7. 成功後にPages deploy

保存済みprospective forecast `reports/live-forecast/` は日次更新で書き換えない。

## 8. 検証方針

未来リーク防止を最優先。

- walk-forward
- latest 252 sessions = Discovery
- それ以前の非重複252-session windows = Validation
- accuracyだけでなくBrier Scoreも確認
- 同じValidation結果を見ながら重みや閾値を後付け調整しない

現行モデルは「高精度モデル完成」ではなく、説明可能で検証可能なbaseline + Analog。

## 9. 主要ファイル

```text
scripts/fetch_market_data.py
scripts/sync_forecast.py
scripts/validate_phase2.py

shared/forecast.json
web/forecast.json
web/index.html
web/app.js
web/styles.css

android/app/src/main/java/jp/xiaqui/marketweather/MainActivity.java
android/app/src/main/assets/yahoo_fetch.html
android/app/build.gradle.kts

docs/TODO.md
docs/forecast-values-guide.md
docs/forecast-algorithm.md
docs/migration.md
```

## 10. 運用上の注意

- Web UIの変更はPages deployで反映される。通常はAPK再build不要。
- Androidの殻、署名、versionCode、権限、WebView設定を変えた場合はAPK buildが必要。
- 現在値と予報値を混同しない。
- Androidの現在値更新でforecast JSONを書き換えない。
- Yahoo失敗時に前回成功値を消さない。
- 429時に即リトライ連打しない。
- keystoreを変更・紛失すると同じ署名系列で上書き更新できなくなる。
- `native-compose` branchに旧Compose版を保全している。

## 11. 次に残っている主なTODO

`docs/TODO.md` を正本とする。特に近いもの:

- 現在値と予報値の役割をUI上でさらに明確化
- 予想レンジを最低 / 最高気温のように直感表示
- 下限 / 上限が価格レンジであることを詳細で明示
- 数日の日次schedule安定運用確認
- Yahoo取得失敗時に前回予報を壊さないことの追加確認
- Provider化によるYahoo依存の分離
- 追加特徴量や別モデルは、現行baselineとの比較を前提に検証

## 12. 標準運用

```text
実装
  ↓
PR作成
  ↓
CI確認
  ↓
実機確認
  ↓
「まじおk」
  ↓
最新head + CI再確認
  ↓
merge
  ↓
Pages deploy確認
  ↓
APKが生成された場合はDrive同一ファイルを上書き
```

mergeは明示承認前に行わない。
