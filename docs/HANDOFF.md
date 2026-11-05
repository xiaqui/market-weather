# Market Weather 引き継ぎ書

最終更新: 2026-09-27

## 1. プロジェクト概要

Market Weather は、日経平均 / NYダウ / USD/JPY / GOLD の4市場について、
次営業日の方向・値幅・荒れやすさを「金融天気予報」として見せる個人利用中心の実験プロジェクト。

表示の正本は GitHub Pages。

- Web: https://xiaqui.github.io/market-weather/
- Android: 上記Pagesを表示する薄いWebViewカプセル
- repository: `xiaqui/market-weather`
- default branch: `main`
- applicationId: `jp.xiaqui.marketweather`
- minSdk: 26
- target / compile SDK: 35

Androidの現在値だけは、Pagesの予報JSONとは別にYahoo Financeから取得して画面へ上書きする。
現在値が更新されても、天気 / 上昇確率 / 予想レンジ / 予報根拠度 / Trend / Analog は変えない。

---

## 2. 現在の予報ロジック

予報入力は確定済み日足のみ。
形成中の日足を予測へ混ぜない。

本番の最終上昇確率は50:50 Ensemble。

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

日経 / Dow / USDJPY / GOLD をまとめた30次元状態を作り、
過去約10年から似た局面を最大30件検索する。

対象市場の休場時間、その間の他市場累積変動も特徴に含む。

詳細:

```text
docs/forecast-values-guide.md
docs/forecast-algorithm.md
```

---

## 3. 天気の意味

天気は最終 `up_probability` から決める。

```text
62%以上        晴れ
54%以上        晴れ時々曇り
46%超～54%未満 曇り
46%以下        雨
```

方向と荒れやすさは別物。

- 天気 = 方向
- risk = ボラティリティ / 荒れやすさ

将来的にriskは「風の強さ」として表現する案があるが未実装。

---

## 4. 予報根拠度 forecast_support

PR #30 で追加済み。
merge commit:

```text
27d10c6b833ef40ff29db5c71faa033373978ffc
```

これは上昇確率でも的中確率でもない。

意味は、

```text
up_probabilityを支える材料が
どの程度揃い、互いに整合しているか
```

を0〜1で表したもの。

主な材料:

- Trend内部一致度 `trend_confidence`
- Trend / Analog の連続的な確率一致度
- Analogの相対距離品質
- Analogの実効サンプルサイズ ESS

現行構成:

```text
forecast_support
= 0.35 × trend_confidence
+ 0.30 × continuous_agreement
+ 0.20 × analog_distance_quality
+ 0.15 × min(1, ESS / 30)
```

Analogを作れない場合は、利用できるTrend成分のみ反映する。

JSONには次が追加済み。

```text
trend_confidence
analog_effective_sample_size
forecast_support
```

旧 `confidence` は互換性のため残っており、
現在はTrend内部一致度と同じ意味。
Ensemble全体の的中確率として解釈しない。

### Ensemble confidence検証の結論

PR #29で複数候補を時系列分離して検証したが、
「confidenceが高い群ほど方向正解率が高い」という関係を市場横断で確認できなかった。

したがって、旧confidenceをEnsemble confidenceへ置き換える案は不採用。

merge commit:

```text
29fe663a7923414d3e56840495d283fba89c494c
```

---

## 5. 現在のカードUI

2026-09-27に「天気アイコン最優先」へ再設計済み。

初回実装:

```text
2b9c6e547b9672106af7bf8ad80b5fd545790b51
天気アイコン優先のカードUIに再設計
```

実機確認後の調整:

```text
234c1c3fddcf74d258e94ae5c6fbb72a5c73b117
天気アイコンを右寄せして区切り線を削除
```

### 現行レイアウト思想

カードは左右構成。

```text
左
(小) 市場名 + Androidでは ↑↓ー%
(中) 基準値 / 現在値
(最小) 予想レンジ

右
(大) 天気アイコン
天気説明 + 予報根拠度%
```

視覚優先順位:

```text
1. 天気アイコン
2. 基準値 / 現在値
3. 天気説明 + 予報根拠度
4. 市場名 + live方向%
5. 予想レンジ
```

ポイント:

- 天気アイコンがカード内最大要素
- 4カード一覧性を維持
- 中央の縦区切り線は削除済み
- 天気アイコンは右寄せ
- カード高はコンパクトなまま
- 初期画面には `up_probability` を重複表示しない
- `forecast_support` は天気説明の横に百分率で表示
- 詳細画面では `予報根拠度` と `Trend一致度` を表示

`docs/TODO.md` の一部UI記述はこの最新状態より古い箇所がある。
画面仕様については実装 + このHANDOFFを優先して確認すること。

---

## 6. 見出し

現在の見出しは概ね次の形式。

```text
次営業日の金融予報 9/26(土) 9:43発表
```

- 「金融天気予報」ではなくコンパクトな「金融予報」
- 日付 + 曜日 + 発表時刻
- `generated_at` をJSTへ変換して表示

---

## 7. Android現在値

Androidでは市場名の横に、
予報生成時の基準値に対する現在値の途中位置を表示する。

```text
↑ 1.24%
ー 0.05%
↓ 0.83%
```

deadband:

```text
+0.1%超   ↑
±0.1%以内 ー
-0.1%未満 ↓
```

これは予報方向ではない。

### 未着手の論点

市場休場中に `ー 0.0%` を出す必要があるか、という話が残っている。

ただし、
「市場が開いていて本当に横ばい」と
「休場だから動いていない」を区別したいので、
単純に0.00%を常時隠すだけでは雑。

必要ならYahoo Chart APIのmarket state / session情報を確認して別タスク化する。

---

## 8. Android現在値取得

表示用WebViewとは別の非表示ローカルWebViewを使用。

```text
android/app/src/main/assets/yahoo_fetch.html
```

JavaScript `fetch()` → Java bridge `AndroidYahoo`。

現行取得先:

```text
nikkei  ^N225
dow     ^DJI
usdjpy  USDJPY=X
gold    GC=F
```

重要:
モデル / 履歴側USDJPYのcanonical symbolは `JPY=X`。
Android現在値取得だけ `USDJPY=X` を使う既存構成になっている。

安定しているため、美観目的でこの二重構成を不用意に統一しない。

挙動:

- 起動時取得
- フォアグラウンド復帰時取得
- 下スワイプで手動更新
- 60秒pollなし
- 4市場を1.5秒間隔
- 10秒timeout
- 429を検出したら残りを止める
- 429後は5分cooldown
- 部分成功を保持
- 最終成功値をSharedPreferencesへ保持
- failureで成功値を消さない
- 画面回転で不要な再取得をしない
- 診断表示は通常非表示

---

## 9. 最新forecast JSON

2026-09-27引き継ぎ時点でrepoにある `shared/forecast.json`:

```text
generated_at: 2026-09-26T00:43:55+00:00
JST:          2026-09-26 09:43:55
```

例:

```text
日経
up_probability 0.7564
weather sunny
forecast_support 0.7905

Dow
up_probability 0.4844
weather cloudy
forecast_support 0.6475

USDJPY
up_probability 0.5294
weather cloudy
forecast_support 0.6643

GOLD
up_probability 0.3329
weather rainy
forecast_support 0.7792
```

forecast値は日次更新で変わるため、この数値自体を仕様値として固定しない。

---

## 10. 日次予報更新

workflow:

```text
.github/workflows/update-daily-forecast.yml
Update Daily Forecast
```

schedule:

```text
30 22 * * 1-5
```

UTC 22:30、JST翌朝7:30頃。

処理:

1. `scripts/fetch_market_data.py`
2. `scripts/sync_forecast.py`
3. `python -m scripts.score_live_forecast`
4. forecast各コピー + prospective history に差分がある場合のみcommit
5. mainへpush
6. 成功後Pages deploy

現在commit対象:

```text
shared/forecast.json
android/app/src/main/assets/forecast.json
android/app/src/test/resources/forecast.json
web/forecast.json
reports/live-forecast-history.json
```

prospective scoring workflow呼び出しは過去に
`python scripts/score_live_forecast.py` でModuleNotFoundErrorになったため、
現在はmodule実行へ修正済み。

---

## 11. prospective validation

最初のprospective forecastは保存済み。

```text
reports/live-forecast/
reports/live-forecast-history.json
```

日次workflowで実績スコアを積む。

方針:

- 保存済みforecastを後から書き換えない
- walk-forward
- 未来リーク禁止
- accuracyだけでなくBrier Scoreも見る
- DiscoveryとValidationを分離
- 同じValidationを見ながら重みを後付け調整しない

次の重要テーマの一つは、
prospective forecastの蓄積と答え合わせを継続運用できること。

---

## 12. APK / Android build

GitHub Actions artifact:

```text
market-weather-debug
```

固定署名対応済み。

Repository Secrets:

```text
KEYSTORE_BASE64
KEYSTORE_PASSWORD
KEY_ALIAS
KEY_PASSWORD
```

keystoreやpasswordはrepoへ入れない。

現在の `versionCode` は2。

Web UIだけの変更では原則APK再build不要。
Pages更新でAndroid WebView側にも反映される。

Androidの殻、権限、WebView設定、署名、versionCode等を変えた場合はAPK buildが必要。

### APK配布

APKはrepository設定の固定配送ファイルへ内容更新し、利用者向けURLを維持する。配送先ID・URL・認証情報はリポジトリへ記録しない。artifact ZIPではなく中の実APKを検証し、現行TASKが配送を含む場合だけ更新・再取得確認する。

---

## 13. Git / TASK.md 運用

repo root:

```text
AGENTS.md
TASK.md
```

運用詳細:

```text
docs/task-md-workflow.md
```

2026-09-27時点で確立したルール:

### タスク種別

```text
新規タスク
既存タスクへの追加
既存タスクへの追加修正
既存タスクの再実行
既存タスクの完了処理
```

タスク種別とGit運用は別軸。

「merge済みだから新規」ではない。
同じ目的なら追加、目的が別なら新規。

### Git運用

メンテナーが作業前に判断してTASK.mdへ明記する。

実装担当（開発担当）は再判定しない。

main直接push向き:

- 文言
- docs
- 軽微な表示調整
- 局所的 / 容易にrevert可能
- 実機で良否を判断しやすい変更

branch + PR向き:

- 内部ロジック
- 予測式
- データ構造
- CI / workflow
- build
- API / auth / 権限
- refactor
- 影響範囲不明
- 複数日にまたがる作業

迷ったらbranch。

### 実行方法

実装担当はAGENTS.mdと現在のTASK.mdを読み、指定Git運用に従って実装・test・commit・pushし、branch指定ならPRを作る。短縮命令や個人的な会話コンテキストをrepositoryの実行条件にしない。

### 現在のTASK.md

mainのTASK.mdは実行中なしを示す。open PRの作業範囲は各PR branch側で管理し、完了済みタスクを再実行しない。

次のCodex作業を始める前に、
TASK.mdを次タスクへ更新すること。

---

## 14. GitHub運用上の注意

`AGENTS.md` のremote fallbackには現在
market-weather固有URLが書かれている。

このrepo内では問題ないが、
AGENTS.mdを他repoへそのままコピーする場合は危険。

汎用運用ではrepo固有remoteを直書きせず、
対象repoを一意に特定できる場合だけremote設定する。

詳細は:

```text
docs/task-md-workflow.md
```

---

## 15. 主要ファイル

```text
AGENTS.md
TASK.md

scripts/fetch_market_data.py
scripts/sync_forecast.py
scripts/score_live_forecast.py
scripts/validate_phase2.py

shared/forecast.json
web/forecast.json
web/index.html
web/app.js
web/styles.css

reports/live-forecast/
reports/live-forecast-history.json

android/app/src/main/java/jp/xiaqui/marketweather/MainActivity.java
android/app/src/main/assets/yahoo_fetch.html
android/app/build.gradle.kts

.github/workflows/update-daily-forecast.yml
.github/workflows/deploy-pages.yml
.github/workflows/build-apk.yml

docs/HANDOFF.md
docs/TODO.md
docs/forecast-values-guide.md
docs/forecast-algorithm.md
docs/task-md-workflow.md
docs/development-environment.md
```

---

## 16. 既知のテスト注意

過去のfull unit suiteでは、
Android Yahoo fetch回帰テストの1件だけ既存failureになることがあった。

原因:
テスト側が旧 `await fetch(url)` を期待している一方、
現在の `yahoo_fetch.html` はAbortControllerを使い、

```js
fetch(url, { signal: controller.signal })
```

になっているため。

新しい変更によるfailureと決めつけず、
まず現行testと実装を確認すること。

関連タスクのtarget test / syntax check / `git diff --check` が通っているかは別途確認する。

---

## 17. 後回しになっている表示案

### 日本円表示オプション

将来案:

```text
currencyMode: native | jpy
changeMode: percent | amount | both
```

- Dow円換算
- GOLD円/g
- 変動率 / 変動額表示

ただし今は後回し。

USDJPY自体は為替レートなので、
単純な「円換算」の枠へ雑に入れないこと。

GOLD円/gなら概ね:

```text
ドル建て金価格 × USDJPY ÷ 31.1034768
```

店頭価格とは税・spread・手数料・公表時刻差がある。

---

## 18. 次に残っている主なテーマ

`docs/TODO.md` を長期TODOの正本とするが、
最近のUI変更で一部表示項目は追従していないので注意。

近いテーマ:

- prospective forecast / scoringの継続運用
- 日次scheduleの安定運用確認
- Yahoo取得失敗時に前回forecastを壊さない確認
- 現在値と予報値の意味をさらに直感的にする
- 予想レンジを最低 / 最高気温的に見せる
- riskを「風の強さ」として表現
- 市場休場時の `ー0.0%` 扱い
- Provider化してYahoo依存を分離
- 追加特徴量 / 別モデルは現行baselineとの独立Validation比較が前提

将来構想:

- 日本セクター天気図
- セクター下落圧力を「雨雲レーダー」表示
- 世界天気図 → 日本への圧力 → 国内セクター予報
- 複数日予報
- 予報と実績の答え合わせ画面

---

## 19. 設計原則

重要なので次スレでも維持する。

1. 予報値とlive現在値を混同しない
2. 形成中足を予測へ混ぜない
3. 未来リークを最優先で防ぐ
4. stableなAndroid current取得を美観目的でrefactorしない
5. 天気アイコンが主役
6. 初期画面は5秒で市場の雰囲気を掴める情報量に抑える
7. 数字を足す前に詳細画面へ逃がせないか考える
8. `forecast_support` は的中確率ではない
9. 検証期間を見ながら後付けでモデルを合わせ込まない
10. TASK.md更新前にCodexへ次作業を投げない

---

## 20. 引き継ぎ直後にやること

新しいスレで作業再開するときは、まず:

1. このHANDOFFを読む
2. GitHubの最新mainを確認
3. `TASK.md` が完了済み内容なら次タスクへ更新
4. `docs/TODO.md` は長期TODOとして参照
5. コード変更前に「新規 / 追加 / 再実行」とGit運用を明示

2026-09-27時点の直近UI実装commit:

```text
234c1c3fddcf74d258e94ae5c6fbb72a5c73b117
天気アイコンを右寄せして区切り線を削除
```



