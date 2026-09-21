# TASK.md

## 目的

Market Weather に、このアプリ固有の予測要素として
**Cross-Asset Historical Analog（金融天気図・過去類似局面）モデル**
を追加する。

現在の Trend baseline は残す。
今回追加するモデルは、日経平均 / NYダウ / USDJPY / GOLD の4市場を
別々に見るのではなく、4市場の相対的な動き・組み合わせを
1枚の「金融天気図」として表現し、

> 今と似た4市場の配置・動きが過去に現れたとき、その翌営業日に各市場がどう動いたか

を検索・集計して予報へ反映する。

単なるRSI/MACD追加や一般的な単一市場テクニカル予測ではなく、
**4市場間の関係性そのものを予測材料にすること**が今回の主眼。

---

## 背景 / 発想

投資家の資金配分は市場間で独立ではない。

例:

- GOLDへ資金が向かう
- 株から資金が抜ける
- ドルから円へ資金が移る
- 円高と日本株の組み合わせが変わる
- 米株横ばい + GOLD上昇 + USDJPY下落のような複合局面が生じる

厳密な「資金保存則」を仮定するものではないが、
投資家のリスク選好や資産配分の変化が複数市場へ同時に現れる、という考え方を使う。

天気予報で気圧・風・雲など複数要素の配置を見て
過去の類似天気図を参照するのと同様に、
金融市場でも4市場の「配置と変化」を比較する。

---

## 現在の実装

現行予測:

- Yahoo Finance 日足
- 1/5/20日騰落率
- 5/20日移動平均乖離
- 5/20日ボラティリティ
- Trend baseline
- walk-forward backtest

詳細は:

`docs/forecast-algorithm.md`

現行Trend baselineは削除しない。
比較対象・フォールバックとして維持する。

---

# 今回の実装

## 1. データ期間を拡張

Historical Analog では類似局面数が必要なため、
現在の `range=1y` では不足する。

Yahoo Finance Chart API から、
可能なら **10年程度の日足** を取得する。

推奨:

```text
interval=1d
range=10y
```

4市場すべてで取得可能か確認し、
取得不能な場合のみ合理的な期間へ短縮する。

現在値表示は従来どおり `regularMarketPrice` を使う。

形成中の日足を確定足として扱わない既存対策は必ず維持する。

---

## 2. 「金融天気図」状態ベクトルを作る

各時点で4市場をまとめて1つの状態ベクトルにする。

生の価格水準は使わない。
時代による価格スケール差を避けるため、
騰落率・移動平均乖離・ボラティリティ等の
無次元または正規化可能な値を使う。

### 各市場ごとの基本状態

最低限、各市場について以下を作る。

- 1日騰落率 / 5日ボラ
- 5日騰落率 / (5日ボラ × √5)
- 20日騰落率 / (20日ボラ × √20)
- 20日移動平均乖離 / 20日ボラ
- 5日ボラ / 20日ボラ

極端値の影響を避けるため、
方向系シグナルは現行baseline同様に適切にclipする。

例:

```text
Nikkei:
  n1, n5, n20, n_ma20, n_vol_ratio

Dow:
  d1, d5, d20, d_ma20, d_vol_ratio

USDJPY:
  u1, u5, u20, u_ma20, u_vol_ratio

Gold:
  g1, g5, g20, g_ma20, g_vol_ratio
```

ここまでで20次元程度。

---

## 3. 市場間の相対関係を明示的に特徴量へ入れる

単に4市場の特徴を連結するだけではなく、
今回の主眼である「絡み合い」を明示的に入れる。

最低限、5日正規化モメンタムについて
4市場の全ペア差分を作る。

4市場なので6組:

```text
Nikkei - Dow
Nikkei - USDJPY
Nikkei - Gold
Dow - USDJPY
Dow - Gold
USDJPY - Gold
```

必要なら20日側にも同様の相対特徴を追加してよいが、
最初から過剰次元にしない。

目的は、
「どれが上がってどれが横ばい / 下がっているか」
という相対配置を距離計算へ反映すること。

---

## 4. 日付・時差・未来データ混入を厳密に扱う

ここは最重要。

日経、米株、為替、金は取引時間・休日が異なるため、
単純に同じ配列indexや同じ日付文字列で結合しない。

各Historical Analog用スナップショットでは、

> そのスナップショット時刻までに、実際に利用可能だった各市場の
> 最新の「確定済み日足」だけ

を使う。

未来の終値を混ぜない。

実装方法はCodex側で最も安全で単純なものを選んでよいが、
以下を満たすこと:

- 形成中日足は除外
- 休日は直近の確定日足を利用可能
- 予測対象日の結果は特徴量に入れない
- backtest時に現在のデータを過去へ漏らさない
- タイムゾーン差をコード上で明示する
- index位置合わせだけで済ませない

この要件を自動テストで守る。

---

## 5. 類似局面検索

現在の金融天気図ベクトルと、
過去の各スナップショットの金融天気図ベクトルを比較する。

初版は説明可能性を優先して、
**k-nearest neighbors型の類似検索** とする。

機械学習ライブラリを必須にはしない。
標準Pythonで十分なら標準Pythonを優先する。

### 距離

初版は標準化された特徴量同士の
Euclidean distanceを基本とする。

ただし特徴量のスケール差が残る場合は、
過去データのみを使った標準化を入れる。

重要:

- 全期間を使って平均・標準偏差を算出しない
- backtest時はその時点より未来の統計量を使わない

---

## 6. 近傍数

初版の既定値:

```text
k = 30
```

ただし利用可能な過去局面が少ない場合に備える。

最低近傍数:

```text
MIN_ANALOGS = 15
```

15件未満ならAnalog予報を無理に出さず、
Trend baselineのみへフォールバックする。

kや最低件数は定数化し、
将来調整できるようにする。

---

## 7. 類似度による重み付け

30件を単純多数決するだけではなく、
近い局面ほど少し強く効くようにする。

推奨:

```text
weight = 1 / (distance + epsilon)
```

などの単純な逆距離重み。

極端な1件だけが支配しないよう、
epsilonやweight capを設けてもよい。

複雑なkernel最適化は今回不要。

---

## 8. Analog上昇確率

各過去類似局面について、
そのスナップショットの「次の確定日足」が
上昇したか下落したかを見る。

市場ごとに別々に集計する。

例:

```text
類似局面 30件

Nikkei:
  上昇 20
  下落 10
  距離加重上昇確率 0.68

Dow:
  上昇 14
  下落 16
  距離加重上昇確率 0.46
```

出力:

```text
analog_probability
analog_count
analog_mean_distance
```

可能なら、
類似局面の翌日平均リターンも算出する。

```text
analog_mean_next_return
```

---

## 9. Trend baselineとAnalogを分けて保持

最初からAnalogでTrend baselineを置き換えない。

JSON上で両方を明示的に残す。

推奨フィールド:

```json
{
  "trend_probability": 0.64,
  "analog_probability": 0.70,
  "analog_count": 30,
  "analog_mean_distance": 1.23,
  "analog_mean_next_return": 0.004,
  "up_probability": 0.67
}
```

既存 `up_probability` は最終予報として維持する。

---

## 10. 初版ensemble

初版は恣意的な最適化をしない。

Analogが有効な場合:

```text
final_probability
= 0.5 × trend_probability
+ 0.5 × analog_probability
```

AnalogがMIN_ANALOGS未満なら:

```text
final_probability
= trend_probability
```

将来backtest結果を見て重みを変更できるよう、
重みは定数化する。

**今回、過去成績に合わせて重みを最適化しない。**

後付けで過学習しないため。

---

## 11. weatherは最終確率から決める

既存のweather分類は、
Trend単独ではなくensemble後の `up_probability` から決める。

riskは当面、
現行20日ボラティリティベースを維持してよい。

予想レンジも今回は既存方式を維持してよい。

Analogの平均翌日リターンをレンジ中心へ反映するのは将来課題とする。

---

## 12. confidenceの扱い

現在の `confidence` は
Trend内部の方向一致度であり、
「予報的中確率」ではない。

今回Analog追加後も、
この意味を曖昧にしない。

最低限:

- 既存Trendの一致度は内部値として残す
- Analog側には `analog_count` と距離情報を持つ
- 最終confidenceを新しく定義する場合は、その式と意味をdocsへ明記

無理に今回final confidenceを高度化しなくてよい。

既存UIの「信頼度100%」が誤解を招く問題は別途扱えるよう、
今回のコード変更で意味をさらに曖昧にしないこと。

---

## 13. walk-forward backtest

Analogモデルも必ずwalk-forwardで検証する。

各予測時点で:

1. その時点までに利用可能な4市場データだけで金融天気図を作る
2. それ以前の局面だけを類似検索対象にする
3. 類似局面の翌日結果を集計
4. その時点のTrend予報とAnalog予報をensemble
5. 実際の次営業日方向と比較

現在以降のAnalog候補を検索対象に含めない。

### 比較出力

市場ごとに最低限:

```text
Trend accuracy
Analog accuracy
Ensemble accuracy
sample count
```

を表示する。

可能ならBrier Scoreも追加する。
実装負荷が小さければ今回入れてよい。

ただし精度が悪くても隠さない。
初版の目的は「法則があるか検証可能にすること」。

---

## 14. 「金融天気図」の説明可能性

詳細画面や将来UIで使えるよう、
予測結果JSONにはAnalogの説明材料を残す。

最低限:

- analog_probability
- analog_count
- analog_mean_distance
- analog_mean_next_return

可能なら、
最も近い過去局面3件程度について
日付と距離を別のdebug/report出力へ残す。

本番JSONが肥大化するなら、
通常forecast.jsonへ全候補を入れる必要はない。

CLI出力または別report JSONでもよい。

---

## 15. UI

今回の主目的は予測エンジン。

ただし既存詳細ダイアログへ簡単に追加できるなら、
以下を表示する。

```text
トレンド予報        64%
類似天気図予報      70%
類似局面            30件
最終予報            67%
```

レイアウトを大きく作り直さない。

トップカードは既存の `up_probability` を表示するだけでよい。

---

## 16. docs更新

以下を更新する。

### `docs/forecast-algorithm.md`

現行Trend baselineに加えて、

- 金融天気図とは何か
- 4市場の関係性を見る理由
- 状態ベクトル
- 相対特徴
- 類似度
- k近傍
- 距離加重
- Trendとのensemble
- walk-forward
- タイムゾーン/休日処理

を人間が読める言葉で追記する。

### 新規または既存docs

必要なら
`docs/cross-asset-weather-map.md`
を作ってもよい。

数式だけでなく、
「日経↑ / Dow→ / USDJPY↓ / Gold↑ のような配置を1枚の天気図として見る」
という発想を必ず説明する。

---

## 17. テスト

最低限以下を追加する。

- 未来データがAnalog候補へ入らない
- 形成中日足が入らない
- 休日/欠損があってもindexずれで他市場の未来値を拾わない
- 金融天気図ベクトルが期待した次元で生成される
- ペア差分が正しく計算される
- 近い局面ほど距離が小さい
- k件を超えて候補を使わない
- MIN_ANALOGS未満でTrendのみへフォールバック
- analog_probabilityが0〜1
- ensemble probabilityが0〜1
- walk-forwardで予測対象日以降を検索しない
- 既存Trend baselineテストを壊さない

---

## 18. 実装上の注意

- pandas / numpy / scikit-learn を新規導入する場合は、本当に必要か検討する
- 標準Pythonで十分なら依存を増やさない
- データ取得と予測ロジックを分離する
- 定数・特徴量名を明示する
- magic numberを散らさない
- 説明可能性を保つ
- 精度を良く見せるための恣意的なparameter tuningをしない
- 未来リーク回避を精度より優先する

---

## 19. 今回やらないこと

- ニュース解析
- SNS解析
- LLM予測
- RSI/MACD大量追加
- Neural Network
- 複雑なGradient Boosting
- パラメータ自動最適化
- 売買シグナル
- 証券会社接続
- Analog予報だけへの全面置換
- 3営業日 / 1週間予報

まず、
**4市場の絡み合いを過去類似局面から読む**
という一本を正しく作る。

---

## 20. GitHub運用

- mainへ直接pushしない
- 専用branchを作る
- 実装
- test
- commit
- push
- Pull Request作成
- GitHub Actions結果を確認
- mergeはしない

Cloud内にAndroid SDKが無い場合はAndroid buildを無理に行わず、
既存ルールどおりGitHub Actionsを正式build確認とする。

---

## 完了条件

- 4市場をまとめた金融天気図ベクトルが生成できる
- 市場間の相対特徴が含まれる
- 過去類似局面を検索できる
- 市場ごとのAnalog上昇確率を計算できる
- Trend / Analog / Ensembleを別々に確認できる
- Analog不足時に安全にTrendへフォールバックする
- walk-forward backtestで未来リークがない
- Trend / Analog / Ensembleの成績比較が出る
- forecast JSONへAnalog情報が追加される
- Web版が既存表示を壊さない
- Python tests成功
- `git diff --check` 成功
- GitHub Actions成功
- docs更新
- PR作成済み

---

## 最後の報告

以下だけ報告する。

- branch名
- commit SHA
- PR番号
- 金融天気図ベクトルの最終構成
- 類似度計算方法
- k / MIN_ANALOGS
- Trend / Analog / Ensembleの各backtest結果
- タイムゾーン・休日・未来リーク対策
- test結果
- Actions結果
- 変更ファイル
- 残課題
