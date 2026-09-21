# 予測アルゴリズム

Market Weather の現在の予測は、AI/LLMや学習済み機械学習モデルではなく、
説明可能な Trend baseline である。

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
range=1y
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

## 12. 現在の位置付け

現在の baseline は以下を満たすための最小構成。

- 説明可能
- 外部大型依存が不要
- 未来データ混入を避けられる
- バックテスト可能
- UIへ安定して予報値を供給できる

今後は、

- RSI
- MACD
- 60日移動平均乖離
- 市場間特徴量
- Logistic Regression
- Gradient Boosting
- アンサンブル
- Brier Score
- Calibration
- レンジ包含率

などを追加し、
baselineと比較しながら改善する。

## 13. 実装ファイル

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
