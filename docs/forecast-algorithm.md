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

この既存26次元は変更せず、予測対象市場ごとに次の4次元を別枠で追加する。

```text
target_hours_since_close
other_market_1_return_since_target_close
other_market_2_return_since_target_close
other_market_3_return_since_target_close
```

したがってAnalog距離へ渡す最終状態は30次元。経過時間は最大168時間、外部市場の
累積returnは各 `-30%〜+30%` にclipする。市場が休んでいる間は価格が止まっているだけで、
外部市場の情報まで止まっているわけではない。その間の他市場変動が再開時にまとめて
反映される可能性があるため、休場期間そのものと、その間に蓄積した外圧を特徴にする。

### 市場ごとのsession close

Yahooの日足ラベルを市場別カレンダーとタイムゾーンから、その日足が利用可能になるUTC時刻へ
変換する。現在日の `currentTradingPeriod.regular.end` を過去全日へ流用しない。

- 日経平均: `Asia/Tokyo` 15:00、2024-11-05以降は15:30
- NYダウ: `America/New_York` 16:00
- USDJPY: `America/New_York` 17:00
- GOLD: `America/New_York` 17:00を安全側の通常終了時刻とする

米国のBlack Friday、7月3日、12月24日の営業日は短縮取引として、Dowは13:00、Goldは
13:30を使う。日足が存在しない祝日を生成することはない。想定外の臨時短縮についても
通常終了時刻を使うため、値を実際より早く利用可能にする方向ではなく、遅らせる安全側になる。
形成中足は時刻変換前に除外する。

### snapshot clock、as-of join、休日差

配列indexや同じcalendar dateでは結合しない。live forecastのclockは、4市場で最後に確定した
close event。過去の各対象市場セッションとwalk-forwardでは、その対象市場の次のcloseより
前に確定した最後のglobal close eventを同じ `snapshot_clock` 関数で選ぶ。このためlive、
過去候補、backtestはいずれも「予測を更新できる最新のglobal close」という同じ規則になる。

各clockでは、そこまでに確定した各市場の最新行をas-ofで取得する。日本休場/米国営業、
米国休場/日本営業、為替だけ、Goldだけが更新された場合も、休場市場は直近確定足を保持する。
ある市場のcloseより後の他市場終値は、その時点のsnapshotには入らない。次のglobal clockへ
進んだ時だけ入り、対象市場のstalenessと累積外部returnも同時に増える。

### 類似度と集計

候補は必ず現在のスナップショットより過去で、かつ候補の次の対象市場終値が現在時刻までに
確定している局面だけとする。候補期間だけの平均と標準偏差で30特徴を標準化し、
30次元の平方差平均の平方根（RMS Euclidean distance）が小さい順に最大 `k = 30` 件を使う。
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

各対象市場の各予測時点で、liveと同じsnapshot clock規則を適用し、そのUTC時刻までに
確定した4市場データだけから状態を作り、
結果まで確定済みの過去局面だけを検索する。Trend、Analog、50/50 Ensembleの方向正解率と
サンプル数を別々にCLIへ表示する。報告期間は直近252セッションとし、それ以前を含む
最大10年の履歴は候補集合として使う。Analog不足時のEnsembleはTrendと同じ値になる。

### Trend / Analog 予報士比較

Trendは対象市場自身の直近の流れを見る予報、Analogは4市場をまとめた金融天気図から
過去の類似局面を探す予報である。Ensembleは両者を50:50で平均した初期比較モデルであり、
今回の診断によって重みや予測ルールは変更しない。

walk-forwardの各予測について、時刻、Trend・Analog・Ensemble確率、実績方向、類似局面数、
平均距離を保持する。同じ未来リーク防止済みレコードから、次をCLIへ出力する。

- Trend↑/Analog↑、Trend↑/Analog↓、Trend↓/Analog↑、Trend↓/Analog↓の4分類
- 一致時と不一致時の件数・実績上昇率・各予報の正解率
- `abs(Trend - 0.5) + abs(Analog - 0.5)`による固定strength bin
  （weak `< 0.10`、medium `< 0.25`、strong `>= 0.25`）
- Analog平均距離をサンプル数で機械的に3分割したclosest / middle / farthest
- Trend、Analog、EnsembleのBrier Score

一致・不一致や強さ、距離別の分析は、将来のconfidenceや最終予報ルールを判断するための
診断に限る。成績に合わせた閾値最適化や、現行予報への条件分岐追加は行っていない。

### 検証フェーズ2: 非重複期間での再現性

最新252対象市場セッション（Window 0）は、既に仮説を発見したDiscovery期間であり、
未使用holdoutではない。`python scripts/validate_phase2.py` はそこから過去へ252セッションずつ、
重複しない最大4個のValidation windowを切り出し、市場ごとの予測時点で利用可能だった情報だけを
使う同一のwalk-forwardを実行する。

生成する`reports/phase2-validation.json`には、window別の正解率、Brier Score、一致・不一致、
paired comparison、固定strength bin、距離3分割、95% Wilson区間、discordant pairのexact binomial
p-valueに加え、always-up、always-down、確率50%固定、各予測時点より前だけの実績上昇率を使う
expanding historical up-rate baselineとの比較と、Validation window間の再現回数を記録する。
単一期間の好成績を「発見」と「再現性」に
分けて扱い、結果を見て同じPR内で30次元金融天気図、閾値、重み、予測ルールを変更しない。

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
