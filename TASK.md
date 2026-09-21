# TASK.md

## 種別

新規タスク

PR #4「金融天気図による過去類似局面予報」はmainへmerge済み。
今回は独立した検証フェーズとして、新しいbranch / 新しいPull Requestで作業する。

# 金融天気図の検証フェーズ2

## 目的

Cross-Asset Historical Analog（金融天気図）が直近252セッションだけに偶然合っていたのか、
別の未使用期間でも同じ傾向を再現するのか検証する。

今回の主目的は、
「AnalogがTrendより再現性のある情報を持っているか」
を確認すること。

予測モデルの改造・最適化はしない。

## 背景

直近252セッションでは以下だった。

- 日経平均: Trend 48.4% / Analog 57.5% / Ensemble 53.2%
- NYダウ: Trend 48.4% / Analog 55.2% / Ensemble 48.0%
- USDJPY: Trend 50.8% / Analog 50.0% / Ensemble 53.6%
- GOLD: Trend 50.0% / Analog 57.5% / Ensemble 52.8%

不一致時:
- 日経平均: Trend 40.7% / Analog 59.3%
- NYダウ: Trend 42.5% / Analog 57.5%
- USDJPY: Trend 50.9% / Analog 49.1% / Ensemble 57.4%
- GOLD: Trend 42.0% / Analog 58.0%

Brier Score:
- 日経平均: Trend 0.3139 / Analog 0.2484 / Ensemble 0.2634
- NYダウ: Trend 0.3139 / Analog 0.2568 / Ensemble 0.2723
- USDJPY: Trend 0.2935 / Analog 0.2552 / Ensemble 0.2607
- GOLD: Trend 0.2861 / Analog 0.2509 / Ensemble 0.2551

4市場すべてでAnalogのBrier ScoreがTrendより良かった。

一方、
- strengthが強いほど精度上昇、という単調関係はない
- Analog距離が近いほど精度上昇、という単調関係もない
- USDJPYは他3市場と挙動が異なる
- 50:50 Ensembleは市場によってAnalogの良さを消すことがある

ことも分かった。

## 重要方針

今回は検証だけ。

以下は変更しない。

- 30次元金融天気図
- k = 30
- MIN_ANALOGS = 15
- 距離計算
- inverse-distance weighting
- snapshot clock
- session close処理
- 休場日処理
- staleness
- accumulated external move
- Trendロジック
- Trend / Analog 50:50 Ensemble
- 本番forecastの計算式
- weather分類

結果が良くても悪くても、このタスク内で本番ルールを変更しない。

## 1. Discovery期間を固定

PR #4で詳しく観察済みの最新252セッションはDiscovery windowとする。
今後これを未使用holdoutとは扱わない。

Discoveryから既に得た仮説を事前固定する。

仮説A:
日経 / Dow / GOLDでは、TrendとAnalogが不一致の時にAnalog側が強い可能性がある。

仮説B:
Analogは確率予測としてTrendよりBrier Scoreが良い可能性がある。

仮説C:
USDJPYは他3市場とは挙動が異なり、単純なAnalog優先では説明できない可能性がある。

仮説D:
Analog distanceと精度は単調関係ではない。

仮説E:
combined strengthと精度も単調関係ではない。

検証結果を見て仮説の意味を後付け変更しない。

## 2. 非重複Validation windowを作る

現在取得している約10年の日足から、
Discovery windowと重複しない過去期間を使う。

最低限、直前の非重複252セッションを1つ目のValidation windowとする。

可能ならさらに前も使い、
合計3〜5個程度の非重複windowで検証する。

例:
- Window 0: 最新252 = Discovery
- Window 1: その直前252 = Validation
- Window 2: さらに前252 = Validation
- Window 3: さらに前252 = Validation
- Window 4: さらに前252 = Validation

市場ごとに営業日数・欠損が違うため、対象市場のセッション単位で区切る。

各windowの予測では、その予測時点より未来の情報を絶対に使わない。
既存のwalk-forward / snapshot clock / as-of / Analog候補制約をそのまま利用する。

## 3. windowごとの診断

各市場・各windowについて最低限:

- Trend accuracy
- Analog accuracy
- Ensemble accuracy
- Trend Brier Score
- Analog Brier Score
- Ensemble Brier Score
- agreement count / accuracy
- disagreement count
- Trend accuracy on disagreement
- Analog accuracy on disagreement
- Ensemble accuracy on disagreement

を出す。

可能なら4分類も維持する。

- Trend↑ / Analog↑
- Trend↑ / Analog↓
- Trend↓ / Analog↑
- Trend↓ / Analog↓

## 4. 仮説A: 不一致時Analog優位の再現性

日経 / Dow / GOLDで、
Analog disagreement accuracy > Trend disagreement accuracy
が複数のValidation windowでも繰り返されるかを見る。

単一windowだけでなく、
何window中何windowで再現したかを市場別にまとめる。

## 5. 仮説B: Brier Score優位の再現性

各Validation windowでTrend / Analog / EnsembleのBrier Scoreを出す。

特に Analog Brier < Trend Brier が、
市場別に何window中何windowで再現するかをまとめる。

## 6. 仮説C: USDJPYの異質性

DiscoveryではUSDJPYだけ、
- 不一致時 Trend 50.9% / Analog 49.1%
- Ensemble 57.4%
- Trend↓ / Analog↓なのにactual up 74.3%
だった。

各Validation windowで最低限:

- overall actual up rate
- Trend↓ / Analog↓ sample count
- Trend↓ / Analog↓ actual up rate
- disagreement Trend accuracy
- disagreement Analog accuracy
- disagreement Ensemble accuracy

を出す。

期間自体のUSDJPY上昇バイアスを確認するため、
各windowの単純actual up rateも必ず併記する。

USDJPY専用ルールは今回作らない。

## 7. 仮説D: Analog距離と精度

既存のclosest / middle / farthest診断を各Validation windowでも実施する。

距離閾値は成績に合わせて最適化しない。

各windowで:
- closest: mean distance / n / Analog accuracy
- middle: mean distance / n / Analog accuracy
- farthest: mean distance / n / Analog accuracy

を出し、
closestが毎回最良か、middleが繰り返し最良か、順位がバラバラかを見る。

## 8. 仮説E: strengthと精度

既存固定binを変更しない。

- weak < 0.10
- medium < 0.25
- strong >= 0.25

各Validation windowでTrend / Analog / Ensemble accuracyを出し、
strongが一貫して良いかを見る。

結果を見てbin境界を変更しない。

## 9. paired comparison

TrendとAnalogは同じ日を予測しているため、
各市場・各windowで以下を数える。

- both correct
- Trend only correct
- Analog only correct
- both wrong

不一致時についても同様に出せるなら出す。

これにより、単なるaccuracy差ではなく
Analogだけ正解する日が本当に多いのか確認する。

## 10. 統計的不確実性

実装負荷が小さければ追加する。

accuracyについて95% Wilson confidence interval。

標準Pythonだけで可能なら、
Trend only correct vs Analog only correct のdiscordant pairに対する
exact binomial p-valueも出してよい。

外部統計ライブラリを新規導入する必要があるなら無理に入れない。

p-valueだけで結論を決めず、
サンプル数・差の大きさ・複数windowでの再現性を主に見る。

## 11. 再現性サマリ

Validation window全体について市場ごとにまとめる。

例:
- Analog overall accuracy > Trend: X / Y windows
- Analog disagreement accuracy > Trend: X / Y windows
- Analog Brier < Trend: X / Y windows

全Validation期間のaggregateも出してよいが、
window別結果を隠してaggregateだけ見せないこと。

## 12. ルール候補は提案まで

Validation結果から、
将来検討すべきルール候補が見えても今回本番コードへ入れない。

例:
- 日経/Dow/Goldでは不一致時Analog優先
- USDJPYだけ50:50維持

などが見えても「次タスク候補」として報告するだけ。

今回のPRでは予測ルール変更禁止。

## 13. 出力

CLIで確認できるようにする。

可能なら、
reports/phase2-validation.md
または
reports/phase2-validation.json
を生成する。

最低限含めるもの:

- window定義
- 各市場各windowの期間
- sample count
- Trend / Analog / Ensemble accuracy
- Brier
- disagreement比較
- paired comparison
- strength
- distance
- USDJPY追加診断
- 再現性サマリ

合理的なサイズならreportをcommitしてよい。

## 14. テスト

最低限:

- 非重複windowが正しく切られる
- DiscoveryとValidationが重複しない
- window内walk-forwardで未来データを使わない
- paired counts合計がsample countと一致
- disagreement paired countsが対象サンプル数と一致
- Wilson CIが既知fixtureで妥当
- Brier既存テスト維持
- distance/strength診断を壊さない
- snapshot clock / session close / holiday回帰テストを壊さない
- 既存28 testsを壊さない

## 15. docs

適切なdocsへフェーズ2の目的を記録する。

特に:
- 最新252セッションはDiscoveryでありholdoutではない
- 別の非重複期間で再現性を見る
- 結果を見ても同じPR内で予測ルールを変更しない
- 単一期間の好成績を「発見」と「再現性」に分けて扱う

ことを明記する。

## 16. GitHub運用

今回は新規タスク。

- main最新から新branchを作る
- mainへ直接pushしない
- 実装
- test
- commit
- push
- 新しいPull Requestを作る
- GitHub Actions確認
- mergeはしない

## 完了条件

- Discovery windowを固定した
- Discoveryと重複しない複数Validation windowを作った
- 市場別・window別Trend / Analog / Ensemble成績が出る
- Brier再現性が出る
- 不一致時Analog優位の再現性が出る
- USDJPYの異質性を別期間で確認できる
- distance非単調性を別期間で確認できる
- strength非単調性を別期間で確認できる
- paired comparisonが出る
- 可能ならconfidence interval / exact paired testが出る
- 予測ロジックは変更していない
- tests成功
- git diff --check成功
- GitHub Actions成功
- docs更新
- 新PR作成済み
- mergeしていない

## 最後の報告

以下を報告する。

- branch名
- commit SHA
- PR番号
- Discovery window
- Validation window一覧
- 各市場・各windowのTrend / Analog / Ensemble accuracy
- 各市場・各windowのBrier Score
- disagreement比較
- paired comparison
- USDJPY追加診断
- distance結果
- strength結果
- 再現性サマリ
- 統計的不確実性（実装した場合）
- test結果
- Actions結果
- 変更ファイル
- 見えてきた傾向
- 次タスク候補
- 予測ルールは変更していないこと
