# 予測アルゴリズム

Market Weather の現在の予測は、説明可能な Trend baseline と
Cross-Asset Historical Analog（金融天気図・過去類似局面）のアンサンブルである。

目的は「高精度を装うこと」ではなく、
未来データ混入を避けながら、なぜその予報になったか説明できる最小構成を作ること。

## 1. 対象市場

- 日経平均: `^N225`
- NYダウ: `^DJI`
- USD/JPY: `JPY=X`
- GOLD: `GC=F`

データ取得元は Yahoo Finance Chart API。

現在の取得条件:

```text
interval=1d
range=10y
```

## 2. 現在値と確定日足を分離する

Yahoo Finance の日足レスポンスには、市場が開いている最中だと
その日の「まだ形成中の日足」が含まれることがある。

形成中の日足を確定終値として予測に使うと、
時刻によって特徴量やバックテスト結果が変わり、翌営業日予報として不適切になる。

そのため現在は次のように分離している。

- 表示用の現在値: `meta.regularMarketPrice`
- 予測・バックテスト用: 確定済み日足だけ

`currentTradingPeriod.regular` の開始・終了時刻と現在時刻を比較し、
進行中の regular session に属する日足は特徴量計算とバックテストから除外する。

## 3. 使用する特徴量

現在の baseline では以下を計算する。

- 1日騰落率
- 5日騰落率
- 20日騰落率
- 5日移動平均乖離率
- 20日移動平均乖離率
- 5日ボラティリティ
- 20日ボラティリティ

### 騰落率

```text
1日騰落率  = current_close / close[-2]  - 1
5日騰落率  = current_close / close[-6]  - 1
20日騰落率 = current_close / close[-21] - 1
```

### 移動平均乖離

```text
5日MA乖離  = current_close / mean(last 5 closes)  - 1
20日MA乖離 = current_close / mean(last 20 closes) - 1
```

### ボラティリティ

日次リターン列を作り、母標準偏差を使用する。

```text
5日ボラティリティ  = pstdev(last 5 daily returns)
20日ボラティリティ = pstdev(last 20 daily returns)
```

## 4. 方向シグナル

方向予測に直接使うのは次の5本。

```text
1日騰落率   / 5日ボラ
5日騰落率   / (5日ボラ × √5)
20日騰落率  / (20日ボラ × √20)
5日MA乖離   / 5日ボラ
20日MA乖離  / 20日ボラ
```

単純な騰落率だけではなく、
「普段の値動きに対してどれくらい強い動きか」に正規化する。

ボラティリティが極端に小さい場合の暴走を防ぐため、
最低日次ボラティリティとして 0.2% を使用する。

```text
MINIMUM_DAILY_VOLATILITY = 0.002
```

また各シグナルは `-3 ～ +3` にクリップする。

```text
SIGNAL_CLIP = 3.0
```

## 5. シグナルの重み

5本のシグナルを以下の重みで合成する。

```text
1日騰落率      0.10
5日騰落率      0.20
20日騰落率     0.25
5日MA乖離      0.15
20日MA乖離     0.30
```

現在は短期の1日値動きより、
20日程度の中期トレンドをやや重く見る設計になっている。

合成値:

```text
score = Σ(weight × clipped_signal)
```

## 6. 上昇確率

合成スコアをそのまま確率にせず、`tanh` に通す。

```text
up_probability
= 0.5 + 0.32 × tanh(score)
```

`tanh` を使う理由は、極端なシグナルでも
0% / 100% のような過度に断定的な値へ張り付きにくくするため。

この式では概ね 18% ～ 82% の範囲に収まる。

## 7. 予想レンジ

予想レンジは現在値と20日ボラティリティから作る。

```text
range_factor
= max(20日ボラ, 0.2%) × 1.28
```

```text
range_low  = current × exp(-range_factor)
range_high = current × exp(+range_factor)
```

`1.28` は「およそ80%程度の1日区間」を意識した初期値。

これは保証区間ではなく、
最近の荒れ具合から見た翌営業日の目安レンジ。

## 8. 信頼度

現在の `confidence` は「予報が当たる確率」ではない。

5本の方向シグナルがどれだけ同じ向きを向いているかと、
履歴データが十分にあるかを組み合わせた内部一致度。

### シグナル一致度

各シグナルを正負だけに変換し、
方向が揃っているほど高くする。

```text
agreement
= abs(sum(signs)) / number_of_signals
```

### データ十分性

60営業日以上あれば満額とする。

```text
sufficiency
= min(1.0, number_of_candles / 60)
```

### confidence

```text
confidence
= sufficiency × (0.5 + 0.5 × agreement)
```

したがって `confidence = 1.0` は
「絶対に当たる」という意味ではなく、
「データ量が十分で、5本の方向シグナルがすべて同方向」
という意味。

UI上の名称は将来、
「信頼度」より「シグナル一致度」等へ変更する余地がある。

## 9. 天気分類

上昇確率から天気を決める。

```text
62%以上        sunny          晴れ
54%以上        partly_cloudy  晴れ時々曇り
46%超～54%未満 cloudy         曇り
46%以下        rainy          雨
```

天気は方向感を表す。

## 10. リスク分類

20日ボラティリティからリスクを決める。

```text
0.8%未満   calm     安定
1.5%未満   normal   通常
2.5%未満   caution  注意
2.5%以上   storm    荒天
```

天気とリスクは別軸。

たとえば、

- 晴れ + 荒天: 上昇方向だが荒い
- 雨 + 安定: 下落方向だが静か

という組み合わせもあり得る。

## 11. walk-forward バックテスト

バックテストは時系列順の walk-forward。

各時点で、

1. その時点までの履歴だけを渡す
2. 翌営業日の上昇/下落を予測
3. 実際の翌営業日の終値方向と比較
4. 1日進めて繰り返す

ランダムシャッフルはしない。

実装上も、

```python
history = candles[:next_index]
prediction = build_prediction(history)
```

のように、予測対象日のデータを入力へ含めない。

初期baselineの方向正解率は概ね50%前後であり、
現時点では「高精度モデル」ではなく
「リークせず正しく検証できる土台」と位置付ける。

## 12. 金融天気図（Cross-Asset Historical Analog）

日経平均↑ / NYダウ→ / USDJPY↓ / GOLD↑のように、4市場の配置と動きを
1枚の「金融天気図」として扱う。各市場を独立に見るのでなく、投資家のリスク選好や
資産配分が複数市場へ同時に現れる可能性を、過去の似た配置から検証するためである。

### 状態ベクトル

各市場について、価格水準を含まない次の5特徴を作る。

```text
1日騰落率 / 5日ボラ
5日騰落率 / (5日ボラ × √5)
20日騰落率 / (20日ボラ × √20)
20日移動平均乖離 / 20日ボラ
5日ボラ / 20日ボラ
```

方向系4特徴は `-3〜3`、ボラ比は `0〜3` に制限する。4市場分の20次元に加え、
5日正規化モメンタムについて全6ペア（日経-Dow、日経-USDJPY、日経-Gold、
Dow-USDJPY、Dow-Gold、USDJPY-Gold）の差を追加し、合計26次元とする。
この差分が「どの市場が相対的に強いか」を距離へ明示的に反映する。

### 日付、時差、休日

配列indexや日付文字列では結合しない。Yahooの各日足ラベルを、APIが返す
`exchangeTimezoneName` と regular session終了時刻から「その終値が利用可能になるUTC時刻」
へ変換する。スナップショット時刻以前に確定した各市場の最新行をas-of結合するため、
休日はその市場の直近確定足を使い、他市場の未来行を拾わない。形成中足は変換前に除外する。

### 類似度と集計

候補は必ず現在のスナップショットより過去で、かつ候補の次の対象市場終値が現在時刻までに
確定している局面だけとする。候補期間だけの平均と標準偏差で26特徴を標準化し、
26次元の平方差平均の平方根（RMS Euclidean distance）が小さい順に最大 `k = 30` 件を使う。
全期間の統計量や現在以降の値では標準化しない。

各候補は `min(4, 1 / (distance + 0.25))` で重み付けし、市場ごとに次の確定足が
上昇した重みの割合を `analog_probability` とする。同じ重みで翌日平均リターンも計算する。
候補が `MIN_ANALOGS = 15` 件未満ならAnalog値は出さず、Trendへフォールバックする。

### アンサンブルと出力

Analogが有効な場合だけ次式を使い、天気はこの最終確率から決める。

```text
up_probability = 0.5 × trend_probability + 0.5 × analog_probability
```

JSONには `trend_probability`、`analog_probability`、`analog_count`、
`analog_mean_distance`、`analog_mean_next_return`、最終値の `up_probability` を分けて残す。
既存の `confidence` は引き続きTrend内部の方向一致度であり、的中確率ではない。

### walk-forward検証

各対象市場の各予測時点で、そのUTC時刻までに確定した4市場データだけから状態を作り、
結果まで確定済みの過去局面だけを検索する。Trend、Analog、50/50 Ensembleの方向正解率と
サンプル数を別々にCLIへ表示する。報告期間は直近252セッションとし、それ以前を含む
最大10年の履歴は候補集合として使う。Analog不足時のEnsembleはTrendと同じ値になる。

## 13. 現在の位置付け

現在の baseline は以下を満たすための最小構成。

- 説明可能
- 外部大型依存が不要
- 未来データ混入を避けられる
- バックテスト可能
- UIへ安定して予報値を供給できる

今後もBrier Score、Calibration、レンジ包含率などを、baselineと比較しながら検証する。

## 14. 実装ファイル

現在の主実装:

```text
scripts/fetch_market_data.py
```

生成先:

```text
shared/forecast.json
web/forecast.json
```

Android APKは現在WebViewカプセルであり、
GitHub Pages版を表示するため、
通常の予測更新ではAPK再ビルドを必要としない。
