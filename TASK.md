# TASK.md

## 目的

Market Weather を「現在値表示」から最初の実予報へ進める。

4市場の日足履歴を取得し、依存の少ない透明な baseline 予測を作り、
`shared/forecast.json` の予測項目を固定ダミー値から実計算値へ置き換える。

対象市場:
- 日経平均 (`^N225`)
- NYダウ (`^DJI`)
- USD/JPY (`JPY=X`)
- GOLD (`GC=F`)

## 現状

- 現在値取得は Yahoo Finance Chart API で実装済み。
- GitHub Actions から Yahoo Finance への実接続確認済み。
- `shared/forecast.json` → Android / Web の同期は実装済み。
- Pages と APK には4市場の実現在値が反映済み。
- `up_probability`, `range_low`, `range_high`, `confidence`, `weather`, `risk` はまだ固定値。

## 今回やること

### 1. 日足履歴取得

Pythonで4市場の日足履歴を取得する。

条件:
- 現在と同じ Yahoo Finance Chart API を利用
- APIキー不要
- まず過去1年程度を取得
- timestamp / open / high / low / close / volume を扱える構造にする
- 欠損値、休日、市場ごとの時差を雑に埋めず、利用可能な実データだけ使う
- 取得失敗時に壊れた予報JSONを生成しない
- 不要な大型依存は追加しない

### 2. 最小特徴量

各市場について最低限、以下を計算する。

- 1日騰落率
- 5日騰落率
- 20日騰落率
- 5日移動平均乖離
- 20日移動平均乖離
- 5日ボラティリティ
- 20日ボラティリティ

計算は未来データを使わないこと。

### 3. baseline 予測

初期版は学習済みMLモデルではなく、説明可能な単純Trend baseline とする。

要件:
- 上昇方向の強さを複数の過去リターン / 移動平均乖離から作る
- `up_probability` は 0〜1 に必ず収める
- 極端に 0 / 1 へ張り付かせない
- `range_low` / `range_high` は現在値と直近ボラティリティから算出
- `confidence` は方向シグナルの一致度とデータ十分性から 0〜1 で算出
- `weather` / `risk` は数値から決定論的に変換
- マジックナンバーは定数化し、コメントまたはREADME/仕様に意味を書く

これは「最初のbaseline」であり、高精度を装わないこと。

### 4. forecast.json を実計算値へ更新

`shared/forecast.json` について以下を実値 / 実計算値へ更新する。

- `current`
- `up_probability`
- `range_low`
- `range_high`
- `confidence`
- `weather`
- `risk`
- `generated_at`

その後 `python scripts/sync_forecast.py` を実行し、

- `android/app/src/main/assets/forecast.json`
- `android/app/src/test/resources/forecast.json`
- `web/forecast.json`

を正本と一致させる。

### 5. 最小バックテスト / sanity check

最低限、未来データ混入を避けた時系列順の確認を追加する。

- 過去データの各時点で、その時点までのデータだけから翌営業日の方向を出す
- 方向正解率を市場別に表示
- サンプル数を表示
- ランダムシャッフルは禁止
- 成績が悪くても隠さない
- 50%未満でも実装失敗扱いにはしない

高度なMLや最適化は今回やらない。

### 6. テスト

最低限以下を確認する。

- 履歴レスポンスの正常 / 欠損ケース
- 特徴量計算
- probability / confidence が 0〜1
- range_low < current < range_high
- weather / risk の変換
- 未来データを参照しないbaselineバックテスト
- forecast生成
- 正本とAndroid/Web JSONの一致
- `git diff --check`
- Android test / assembleDebug

## UI

既存の画面構成・デザインは変更しない。

予測値が実計算値になれば、現行UIへそのまま表示する。

## GitHub運用

- main へ直接pushしない
- 専用branchを作る
- commit / push
- 新しいPull Requestを作る
- Actionsが成功することを確認する
- 既存の `Verify Market Data` を壊さない

## 完了条件

- 4市場の日足履歴を取得できる
- 最小特徴量が計算できる
- 4市場すべての予測項目が固定ダミー値ではなく実計算値になる
- baselineバックテスト結果が市場別に出る
- Android / Web JSON が正本と一致する
- Pythonテスト成功
- Android build成功
- `git diff --check` 成功
- PR作成済み

## 最後の報告

以下だけ報告する。

- branch名
- commit SHA
- PR番号
- 4市場の最新予報値
- 4市場のbaseline方向正解率とサンプル数
- test/build結果
- 変更ファイル
- 残課題
