# TASK.md

## 目的

PR #4「金融天気図による過去類似局面予報を追加」の追加検証として、
Trend / Analog / Ensemble の成績を「単純な全体正解率」だけでなく、
**TrendとAnalogが一致した時・割れた時・確信が強い時・類似度が高い時**
に分解して確認できる診断レポートを追加する。

今回の目的はモデルを調整することではない。

- 重みを変えない
- kを変えない
- 特徴量を変えない
- 閾値を成績に合わせて最適化しない
- 現行50:50 Ensembleを変更しない

まず、今ある2人の「予報士」がどんな場面で当たりやすいかを観察可能にする。

---

## 背景

現在の直近252セッションbacktestでは、

- 日経: Trend 48.4% / Analog 57.5% / Ensemble 53.2%
- NYダウ: Trend 48.4% / Analog 55.2% / Ensemble 48.0%
- USDJPY: Trend 50.8% / Analog 50.0% / Ensemble 53.6%
- GOLD: Trend 50.0% / Analog 57.5% / Ensemble 52.8%

特にNYダウではAnalog単独が55.2%なのに、
50:50 Ensembleでは48.0%へ悪化している。

このため、
「常にTrendとAnalogを平均すればよい」
とは限らない。

次に確認したいのは、

- TrendとAnalogが同じ方向を向いた時は強いのか
- 意見が割れた時はどちらが強いのか
- 両者が強く一致した時は本当に精度が上がるのか
- Analogの類似度が高い時は精度が上がるのか

という条件別成績。

---

## 1. walk-forwardの各予測レコードを記録可能にする

既存の未来リークなしwalk-forwardをそのまま使い、
各市場・各予測時点について最低限次を保持できるようにする。

```text
date / timestamp
trend_probability
analog_probability
ensemble_probability
actual_up
analog_count
analog_mean_distance
```

Analogが利用不能なケースは明示する。

本番forecast JSONへ全履歴を入れる必要はない。
backtest診断用の内部構造・CLI出力・別report JSONなど、
保守しやすい方法を選んでよい。

---

## 2. Trend / Analog 一致・不一致の4分類

各予測を50%境界で次の4群に分ける。

```text
A: Trend ↑ / Analog ↑
B: Trend ↑ / Analog ↓
C: Trend ↓ / Analog ↑
D: Trend ↓ / Analog ↓
```

市場ごとに各群について最低限次を出す。

```text
sample count
actual up rate
Trend accuracy
Analog accuracy
Ensemble accuracy
```

例:

```text
Nikkei
Trend↑ / Analog↑
  n=72
  actual_up=65.3%
  Trend=65.3%
  Analog=65.3%
  Ensemble=65.3%

Trend↑ / Analog↓
  n=58
  actual_up=39.7%
  Trend=39.7%
  Analog=60.3%
  Ensemble=...
```

特に「不一致時にTrend側とAnalog側のどちらが優位か」を確認できること。

---

## 3. 一致 vs 不一致の集約

4分類とは別に、

```text
Agreement:
  TrendとAnalogが同方向

Disagreement:
  TrendとAnalogが逆方向
```

の2群へまとめた成績も出す。

各市場について:

```text
agreement sample count
agreement accuracy
disagreement sample count
Trend accuracy on disagreement
Analog accuracy on disagreement
Ensemble accuracy on disagreement
```

ここは将来の「信頼度」設計候補になるため重要。

---

## 4. 予報の強さを分析する

同じ「両方↑」でも、

```text
Trend 51% / Analog 52%
```

と

```text
Trend 72% / Analog 68%
```

では意味が違う。

まず以下の単純な強さ指標を診断用に計算する。

```text
trend_strength  = abs(trend_probability  - 0.5)
analog_strength = abs(analog_probability - 0.5)
combined_strength = trend_strength + analog_strength
```

既存予報ロジックには使わない。

### 固定bin

後付け最適化を避けるため、
分位点で「成績が良く見えるように」切らない。

固定幅で例えば次の3群に分ける。

```text
weak:   combined_strength < 0.10
medium: 0.10 <= combined_strength < 0.25
strong: combined_strength >= 0.25
```

この閾値が実データ上不合理な場合のみ、
理由を明示して単純な固定値へ変更してよい。

各binで:

```text
sample count
actual up rate
Trend accuracy
Analog accuracy
Ensemble accuracy
```

を出す。

Agreement群だけを対象にした
weak / medium / strong の成績も出せるなら追加する。

---

## 5. Analog類似度と成績の関係

Analogには `analog_mean_distance` がある。

「過去の天気図に非常によく似ている時ほど当たりやすいか」
を確認する。

### 重要

distanceの閾値を成績に合わせて最適化しない。

診断用には、
各市場のwalk-forward対象サンプルを
**距離の3分位または4分位**で機械的に分割してよい。

これは「しきい値を予測ルールに使う」のではなく、
単に低距離 / 中距離 / 高距離で成績差を見る診断なので可。

最低限:

```text
closest group
middle group
farthest group
```

について、

```text
sample count
mean distance
Analog accuracy
Ensemble accuracy
actual up rate
```

を出す。

可能なら `analog_count` が30未満になるケースの成績も別表示する。

---

## 6. 確率予測としての評価

実装負荷が小さければ、
各市場について次を追加する。

- Trend Brier Score
- Analog Brier Score
- Ensemble Brier Score

Brier Score:

```text
mean((probability - actual)^2)
```

actualは上昇=1、非上昇=0。

これは方向正解率と違って、
60%予報と90%予報の「外し方」も評価できる。

未来リークなしの同じwalk-forwardレコードから算出する。

今回はCalibration曲線の本格実装までは不要。
ただし簡単なら、
40-50 / 50-60 / 60-70 / 70-80%程度の固定bin別actual up rateを
補助出力してもよい。

---

## 7. レポート形式

CLIで読みやすく確認できることを優先する。

必要なら別ファイルとして、

```text
reports/backtest-diagnostics.json
```

または

```text
reports/backtest-diagnostics.md
```

を生成してもよい。

ただし実行のたびに巨大な履歴をGit管理する必要はない。
生成物をcommitするかどうかは、既存repo方針に合わせて判断する。

最低限CLIで市場ごとの診断が確認できればよい。

---

## 8. 今回は予測ロジックを変更しない

重要。

診断結果を見て、

- Analogを70%にする
- Trendを捨てる
- NYダウだけAnalogにする
- 距離が近い時だけAnalogを使う
- 一致時だけ強気にする

などのルール変更は今回行わない。

今回のPRでやるのは
**観測とレポートだけ**。

結果を見て、別の仕様判断として次タスクを作る。

---

## 9. 既存の金融天気図実装を壊さない

PR #4で修正済みの以下を維持する。

- 共通snapshot clock
- 市場別session close
- 短縮取引日
- 日経2024年取引時間延長
- 日本/米国休場差
- as-of join
- staleness
- accumulated external move
- 未来リーク防止
- 30次元Analog状態
- k=30
- MIN_ANALOGS=15
- 50:50 Ensemble

---

## 10. テスト

最低限以下を追加する。

- 4分類が期待通りに振り分けられる
- agreement / disagreement集計が正しい
- combined_strengthが正しく計算される
- strength bin境界が正しい
- distance groupのサンプル総数が元サンプル数と一致する
- Brier Scoreが既知の小さなfixtureで正しい
- Analog Noneのケースを安全に除外/扱える
- 既存walk-forward未来リークテストを壊さない
- 既存24 testsを壊さない

---

## 11. docs

`docs/forecast-algorithm.md` または適切なdocsへ、
以下を短く追記する。

- Trend = 単一市場自身の最近の流れ
- Analog = 4市場の金融天気図から過去類似局面を探す予報
- Ensemble = 現在はTrend/Analogを50:50平均した初期比較モデル
- 一致/不一致分析は、将来のconfidenceや最終予報ルールを決めるための診断であり、
  現時点では予測ロジックへ反映していない

---

## 12. GitHub運用

- PR #4 の同じbranch `金融天気図` を更新する
- 新PRを作らない
- mainへ直接pushしない
- PR #4最新headをcheckout/更新して作業する
- commit / push
- GitHub Actions確認
- mergeはしない

---

## 完了条件

- walk-forward各予測レコードを診断可能
- Trend↑/Analog↑、Trend↑/Analog↓、Trend↓/Analog↑、Trend↓/Analog↓ の4分類成績が出る
- agreement / disagreement成績が出る
- weak / medium / strong成績が出る
- Analog距離別成績が出る
- 可能ならBrier Scoreが出る
- 市場別に結果を比較できる
- 予測ロジック自体は変更していない
- tests成功
- `git diff --check`成功
- GitHub Actions成功
- docs更新
- PR #4更新済み
- mergeしていない

---

## 最後の報告

以下を報告する。

- commit SHA
- PR #4最新head
- 追加した診断項目
- 市場別4分類結果
- agreement / disagreement結果
- strength別結果
- Analog距離別結果
- Brier Score（実装した場合）
- test結果
- Actions結果
- 変更ファイル
- 見えてきた傾向
- ただし予測ルールは変更していないこと
