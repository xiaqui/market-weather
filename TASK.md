# TASK.md

## 種別

既存タスクへの追加修正

# Ensemble最終予報のconfidence設計・実装

## Git運用

branch作業。

理由:
- 予測ロジックの内部計算に触れる
- forecast JSONの `confidence` の意味を変更する
- Trend / Analog / Ensembleの診断値とUI表示へ波及する
- テスト・ドキュメントを含めてコード検収が必要

専用branchで作業し、Pull Requestを作成すること。
mainへ直接pushしない。

推奨branch名:

```text
feature/ensemble-confidence
```

## 背景

現在の `confidence` は Ensemble 最終予報の信頼度ではない。

現行 `build_prediction()` では、Trendが使う5本の方向シグナルについて、

- シグナルの方向一致度
- 履歴量の十分性

から `confidence` を計算している。

その後 `build_cross_asset_predictions()` で Trend と Analog を50:50で合成し、
`up_probability` と `weather` は最終Ensemble値へ置き換えているが、
`confidence` はTrend由来の値のまま残っている。

そのため現在のJSONは、

```text
weather / up_probability = Ensemble最終予報
confidence              = Trend単独の内部一致度
```

という意味の不一致がある。

## 目的

Trend単独の内部一致度と、
Ensemble最終予報についての「確からしさ」を分離する。

最終的に:

```text
trend_confidence
= Trend内部のシグナル一致度

confidence
= Ensemble最終予報のconfidence
```

とする。

ただし `confidence` は「的中確率」ではない。
UI・docsでもその誤解を招かないようにする。

## 1. 既存Trend confidenceを保存する

現行 `build_prediction()` の confidence 計算ロジック自体は捨てない。

既存の意味を `trend_confidence` として明示的に保持する。

基本方針:

```text
現行 confidence
→ trend_confidence
```

Trend-only処理・単体テストで必要なら、
互換性を壊さない範囲で一時的に内部値を扱ってよい。

ただし最終的な `build_cross_asset_predictions()` の出力では、
`confidence` はEnsemble用の値にする。

## 2. Ensemble confidenceの材料

以下を候補として使う。

### A. Trend confidence

- 既存5シグナルの方向一致度
- 履歴十分性

これは `trend_confidence` として保持する。

### B. Trend / Analog の一致度

Trend probability と Analog probability が近く、
かつ同じ方向を示しているほどconfidenceを高くする材料にする。

例:

```text
Trend 0.68 / Analog 0.72
→ 一致度 高

Trend 0.68 / Analog 0.32
→ 一致度 低
```

単に「同じ上下方向か」だけではなく、
確率差も反映すること。

### C. Analogの量

`analog_count` を利用する。

- 候補不足
- MIN_ANALOGSぎりぎり
- ANALOG_Kまで十分

を区別できること。

### D. Analogの類似度

`analog_mean_distance` を利用候補とする。

ただし距離の絶対値に根拠のない固定閾値を置かないこと。

可能なら既存のwalk-forward / historical statesを利用し、
その市場・その時点までに得られる距離分布に対して相対評価するなど、
leak-safeで説明可能な正規化を検討する。

## 3. 重要: いきなり恣意的な式を本番採用しない

最初に候補式を実装または診断コード化し、
walk-forwardデータで以下を確認する。

- confidenceが高い群ほど実際の方向正解率が高くなる傾向があるか
- 低confidence群との差があるか
- 4市場で極端に挙動が違わないか
- confidenceがほぼ常時高止まり / 低止まりしないか
- Trend / Analog disagreement時に適切に下がるか
- Analog不足時の挙動が自然か

最低限、confidenceをいくつかのbucketへ分けて、
各bucketの件数と方向正解率を診断すること。

例:

```text
0.0-0.4
0.4-0.6
0.6-0.8
0.8-1.0
```

bucket境界は診断用なので、必要ならより適切な区切りへ変更してよい。

診断結果をPR本文へ記載する。

## 4. Analogなしの場合

Analogが `None` の場合は最終予報がTrendのみになる。

この場合:

- `trend_confidence` はそのまま利用可能
- Ensemble confidenceはTrend-only fallbackであることを明確に扱う
- Analogが存在するケースと同じ式へ無理に0埋めしない

挙動をテストで固定すること。

## 5. JSON

最終forecast JSONでは最低限:

```json
{
  "trend_confidence": 0.00,
  "confidence": 0.00
}
```

を持つ。

既存の:

- trend_probability
- analog_probability
- analog_count
- analog_mean_distance
- up_probability
- weather
- range_low / range_high
- risk

の意味は変更しない。

必要ならconfidence診断用の内部値をPython内部に追加してよいが、
説明価値の低い中間値をforecast JSONへ大量に露出させない。

## 6. UI

詳細ダイアログの現行:

```text
信頼度 xx%
```

は、新しいEnsemble confidenceを表示する。

ただし「的中確率」と誤解しにくい名称を検討する。

第一候補:

```text
予報信頼度
```

または、より正確で短い名称があればPRで提案してよい。

Trend confidenceは通常の詳細画面へ必ずしも追加しなくてよい。
診断値としてJSONに保持する。

カード表面にはconfidenceを戻さない。

## 7. docs

最低限以下を更新する。

```text
docs/forecast-values-guide.md
docs/forecast-algorithm.md
docs/TODO.md
```

説明では、

- confidenceは的中確率ではない
- Trend confidenceとEnsemble confidenceを分離した
- Ensemble confidenceが何を材料にしているか
- 高confidenceでも結果を保証しない

を明記する。

TODOでは、完了した項目のみ[x]にする。

## 8. prospective / scoringとの関係

既存prospective forecastや保存済みJSONには旧confidenceが残っている。

過去保存済みファイルを一括書き換えしない。

新旧confidenceの意味が途中で変わることを、
必要ならdocsまたはscoring側の説明へ明記する。

履歴比較でconfidenceを使う場合、
旧値と新値を同一指標として無条件に比較しないこと。

## 9. バックテスト上の注意

未来情報をconfidence計算へ使わない。

Analog distanceの基準化やconfidence calibrationに実績を使う場合も、
各walk-forward時点より未来の結果・分布を参照しないこと。

現在のleak-safe制約を維持する。

## 10. 触らないもの

今回変更しない:

- Trend probabilityの計算式
- Analog probabilityの計算式
- Trend / Analogの50:50 weight
- weather閾値
- range計算
- risk計算
- Yahoo取得処理
- Android Yahoo現在値取得
- Android refresh挙動
- 表示オプション
- 円換算
- riskの風表現
- セクター雨雲レーダー

confidence以外の予測性能改善を混ぜない。

## 11. テスト

最低限:

- `trend_confidence` が0〜1
- 新しい `confidence` が0〜1
- Trend / Analogが近い場合は、他条件同一なら disagreementケースより低くならない
- Trend / Analogが大きく対立する場合にconfidenceが下がる
- Analog件数が少ないケースを適切に扱う
- Analogなしfallback
- forecast JSON同期先に新フィールドが反映される
- UI詳細が新confidenceを読む
- 既存weather / up_probability / range / riskが意図せず変化しない
- leak-safe回帰テスト
- `python -m unittest discover -s tests -p 'test_*.py'`
- `git diff --check`

既知の無関係failureがある場合は切り分けて報告する。

## 12. PRで必ず報告するもの

- 採用したconfidence式
- 各構成要素と重み
- その式を選んだ理由
- 4市場のwalk-forward confidence bucket診断
- Trend / Analog disagreement時の挙動
- Analogなし時の挙動
- 旧confidenceとの意味の違い
- 変更ファイル
- test結果
- 今後calibrationが必要な点

## 完了条件

- 旧Trend confidenceが `trend_confidence` として保存される
- `confidence` がEnsemble最終予報用の値になる
- 根拠のない固定値だけでconfidenceを作らない
- walk-forward診断で挙動を確認済み
- confidenceが的中確率ではないことをUI/docsで明示
- 予報ロジックのうちconfidence以外を意図せず変更していない
- branchへcommit/push
- PR作成
- mainへはmergeしない

## 最後の報告

以下を報告する。

- Git運用: branch
- branch名
- commit SHA
- PR番号
- confidence式
- walk-forward診断結果
- test結果
- 変更ファイル
- 残課題


## 追加修正指示: PR #29 confidence設計の再検討

PR #29 の現行実装は、そのままmergeしない。
現行式は候補Aとして残し、診断・比較対象にすること。

### 問題点

現行PRのwalk-forward bucket診断では、confidenceが高いほど方向正解率が高くなる単調な傾向が確認できていない。

特にUSD/JPYでは、confidenceが高いbucketほど方向正解率が低下している。

また、現行252件では analog_count が全件30件であり、

```text
0.15 × min(1, analog_count / 30)
```

が実質的に全件固定加点となっている。
この状態ではAnalog件数成分はconfidenceの識別力に寄与していない。

そのため、現行値を `予報信頼度 xx%` として本番採用するのは見送る。

### 修正方針

1. 現行式を候補Aとして保持する。
2. confidenceの候補式を複数比較する。
3. 重みや式の選定に使う期間と、評価に使う期間を分離する。
4. 同じwalk-forwardデータで重みを選び、その同じデータだけで良し悪しを判断しない。
5. 時系列順にtrain / validationを分離し、未来情報を使わない。
6. validation側で「高confidence群ほど実績方向正解率が高いか」を主に確認する。
7. 単調性、または少なくとも低confidence群より高confidence群が明確に良い傾向を確認できない場合、`予報信頼度` として本番採用しない。

### 候補式で検討するもの

少なくとも以下を比較する。

- Trend confidenceのみ
- Trend confidence + Trend/Analog agreement
- Trend confidence + agreement + Analog distance quality
- 現行候補A
- analog_count成分を除いた式

analog_countは、実データ上ほぼ常に30で識別力がないなら、
本番式から外すか、将来不足ケースが実際に現れた時に再導入すること。

「使える特徴量だから入れる」ではなく、
実際にconfidenceの識別力へ寄与するかで判断する。

### 評価方法

各市場ごとに時系列でDiscovery/TrainとValidationを分ける。

既存の非重複Validation windowが利用可能なら、それを優先的に活用する。

各候補式について最低限:

- bucketごとの件数
- bucketごとの方向正解率
- confidence平均
- confidence分布
- 低confidence群と高confidence群の方向正解率差
- 市場別の挙動
- 全市場統合での挙動

を比較する。

bucketは固定の0.2刻みだけにこだわらず、
件数が極端に偏る場合は分位bucket等も併用してよい。

### 重要: confidenceと的中確率を混同しない

今回の目的は「的中確率そのもの」を作ることではない。

ただし `予報信頼度` と表示する以上、
高い値が低い値より実績上も多少は信頼できる方向へ並ぶ必要がある。

その関係が確認できない場合は、
以下のどちらかにすること。

- confidenceの本番採用を見送る
- 表示名を `モデル一致度` 等へ変更し、予報の信頼性を直接表す値ではないことを明確化する

表示名だけで問題を隠さないこと。

### PR #29のUI変更について

現行PRの

```text
予報信頼度（的中確率ではありません）
```

は、validationで妥当性を確認できるまでは確定仕様にしない。

候補式の検証結果に応じて、

```text
予報信頼度
```

または

```text
モデル一致度
```

等を選ぶ。

カード表面には引き続きconfidenceを出さない。

### JSON互換

`trend_confidence` の追加自体は維持してよい。

ただし新しい `confidence` を本番採用できない場合は、
旧Trend confidenceを新定義のconfidenceとして上書きしない。

その場合は、
- `trend_confidence` のみ追加
- `confidence` は旧定義維持、または移行を保留
のどちらが互換性上安全か検討し、PRで説明する。

過去forecastは書き換えない。

### 完了条件の追加

以下を満たすまでPR #29をmerge可能としない。

- 現行候補A以外の候補式も比較済み
- train / validationを時系列分離
- validation結果をPR本文に記載
- analog_count固定加点問題を解消
- 高confidence群が低confidence群より悪化する市場が残る場合、その理由と扱いを明示
- `予報信頼度` と呼べる根拠が弱い場合は無理にその名称を採用しない
- confidence以外の予測ロジックは変更しない

### PR本文で追加報告するもの

- 候補A〜各候補式
- train / validationの期間
- 各市場のvalidation bucket結果
- 高/低confidence群の差
- analog_count成分を残す/外す理由
- 最終採用式、または採用見送り判断
- 最終表示名
