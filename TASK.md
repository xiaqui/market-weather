# TASK.md

## 種別

新規タスク

# 上昇確率の「予報根拠度」設計・実装

## Git運用

branch作業。

理由:
- 予測JSONへ新しい意味の指標を追加する
- Trend / Analog / Ensembleの内部診断値を組み合わせる
- UI・docs・testsへ波及する
- 数式と意味のレビューが必要

mainへ直接pushしない。
専用branchで作業し、Pull Requestを作成すること。

推奨branch名:

```text
feature/forecast-support
```

## 背景

現在の金融天気予報では、

```text
Trend probability
        \
         + 50:50 Ensemble
        /
Analog probability
        ↓
up_probability
        ↓
weather
```

という流れで最終予報を作っている。

`up_probability` は次営業日の終値が上がる方向のモデル出力であり、
weather はそれを人間向けに段階化した表示である。

一方、ユーザーが知りたい別軸として、

```text
「この up_probability は、
 どれだけ十分で整合した材料から出ているのか」
```

がある。

これは、

- 的中確率
- 上昇確率そのもの
- Trend単独のconfidence

のどれとも異なる。

前タスク/PR #29ではEnsemble confidenceを
「高いほど実績正解率が高い指標」として設計しようとしたが、
時系列分離validationで市場横断の再現性を確認できず、本番採用を見送った。

今回の目的はそこを再挑戦することではない。

## 目的

`up_probability` を支える材料の

- 十分さ
- 一致度
- 類似局面の質
- 予報構成の安定性

を表す新しい指標を設計する。

内部名称:

```text
forecast_support
```

UI第一候補:

```text
予報根拠度
```

とする。

### 意味

例:

```text
up_probability = 0.68
forecast_support = 高

→ 上昇方向68%という予報で、
  その68%を支える材料も比較的よく揃っている
```

```text
up_probability = 0.68
forecast_support = 低

→ 数値上は68%だが、
  Trend/Analogの食い違い、Analog品質不足などがあり、
  68%という値の根拠は弱い
```

## 重要な非目的

`forecast_support` は以下ではない。

- 的中確率
- 「68%の予報が実際に68%当たる」ことを保証するcalibration値
- up_probabilityの置き換え
- Trend / Analogの重み最適化
- 予測精度改善そのもの

「高supportほど必ず当たる」ことを本指標の定義条件にしない。

ただし、将来prospective validationで
supportと実績成績の関係を見ることは可能。
今回はそれを本指標の成立条件にはしない。

## 1. 既存値との役割分離

### up_probability

最終Ensembleの上昇方向確率出力。

```text
Trend 50% + Analog 50%
```

現行仕様を変更しない。

### weather

`up_probability` から決める人間向けカテゴリ。

現行閾値を変更しない。

### trend_confidence

Trend内部の5シグナル一致度 + 履歴十分性。

PR #29で明示化済み。
現行計算を変更しない。

### confidence

互換性のため現時点では旧Trend内部一致度の意味を維持している。

今回、`confidence` の意味を再び変更しない。
新指標は別フィールド `forecast_support` として追加する。

## 2. forecast_support の材料

候補材料は以下。

### A. Trend内部の根拠

`trend_confidence` を使う。

意味:

- Trendを構成する5シグナルがどの程度同方向か
- 履歴量が十分か

### B. Trend / Analog の整合性

`trend_probability` と `analog_probability` の差を見る。

基本原則:

- 近いほどsupportを高くする
- 大きく反対するほどsupportを下げる
- 0.5境界を跨いだ瞬間に大きく不連続になる式を避ける
- 確率差が連続的に反映されること

例:

```text
Trend 0.68 / Analog 0.72
→ 高い整合性

Trend 0.68 / Analog 0.52
→ 中程度

Trend 0.68 / Analog 0.32
→ 低い整合性
```

### C. Analogの質

raw `analog_count` は現状ほぼ常に `ANALOG_K = 30` であり、
PR #29のvalidationでも全件30だった。

したがって raw count を固定加点として使わない。

代わりに、Analogの質を表せる材料を検討する。

優先候補:

- `analog_mean_distance`
- query時点までの候補距離分布に対する相対的な近さ
- nearest weightsの集中度 / effective sample size
- Analog 30件の距離ばらつき

### D. Analogの有効サンプル量

単なる件数30ではなく、
重み付きAnalogが実質何件で支えられているかを見る。

可能なら effective sample size を使う。

例:

```text
ESS = (sum(weights)^2) / sum(weights^2)
```

30件すべてが似た重みならESSは高い。
1〜2件に重みが極端に集中しているならESSは低い。

これにより、

```text
analog_count = 30
```

でも実質的な根拠量を区別できる。

### E. データ不足 / Analogなし

Analogが作れない場合は、
Trend-only予報になる。

この場合に `forecast_support = trend_confidence` と単純コピーするかは
自動決定しない。

Trend-onlyであること自体をsupport低下要因として扱う案も比較する。

例:

```text
Trend-only support
= trend_confidence × fallback_penalty
```

ただし根拠のない penalty 固定値を決め打ちしない。
意味・テスト可能性を優先する。

## 3. weather境界との関係

`forecast_support` は本質的には
`up_probability` の根拠の強さを表す。

weatherカテゴリ境界からの距離そのものは、
根拠の質とは別概念なので、基本式へ無条件に混ぜない。

例:

```text
62.1% → 晴れ
79.0% → 晴れ
```

この2つは「晴れカテゴリの安定性」は違うが、
材料の十分さが同じならforecast_supportまで違う必要はない。

必要なら別診断値として、

```text
weather_margin
```

または

```text
weather_stability
```

を内部計算してもよい。

ただし今回の主指標 `forecast_support` と混同しない。

## 4. 候補式の比較

いきなり1本の式へ固定しない。

少なくとも以下を比較する。

### Candidate A

```text
Trend confidence
+ Trend/Analog agreement
```

### Candidate B

```text
Trend confidence
+ agreement
+ Analog relative distance quality
```

### Candidate C

```text
Trend confidence
+ agreement
+ Analog relative distance quality
+ Analog effective sample size
```

重みは説明可能な少数の値に限定する。

PR #29の旧候補式をそのまま再利用しない。
特に `analog_count / 30` 固定加点は使用しない。

## 5. 評価方法

今回の評価目的は「的中率の単調性」ではなく、
指標が意図した構造を正しく表すかを見ること。

### 必須の構造テスト

他条件が同じなら:

- Trend/Analogが近いほどsupportが高い
- Trend/Analogが大きく食い違うほどsupportが低い
- Analog距離品質が悪いほどsupportが低い
- ESSが低いほどsupportが低い
- Trend confidenceが低いほどsupportが低い
- 0.5境界の微小な跨ぎでsupportが不自然にジャンプしない

### 分布診断

walk-forwardデータで:

- 0〜1の範囲に収まる
- ほぼ全件0.8〜1.0等に高止まりしない
- ほぼ全件同値にならない
- 市場ごとの分布が極端に破綻しない
- disagreement局面で実際に低下する
- Analog品質が弱い局面で低下する

を確認する。

### 実績との関係

方向正解率との関係は参考診断として出してよい。

ただし、

```text
高support群ほど高正解率でなければ失敗
```

とはしない。

理由:
本指標は「材料の強さ」を表すものであり、
「的中確率」を直接推定するものではないため。

将来、prospectiveデータが十分蓄積した後に
support別成績を評価する余地を残す。

## 6. 値のスケール

内部値は原則0〜1。

ただしUIでいきなり `83%` のようなpercentage表示をすると
的中確率と誤解されやすい。

そのため初期UIは数値%ではなく、
段階表示を第一候補とする。

例:

```text
予報根拠度: 高
予報根拠度: 中
予報根拠度: 低
```

内部JSONでは0〜1を保持する。

段階閾値は分布診断を見て決める。
恣意的に 0.33 / 0.66 固定へしない。

候補:
- historical分布の分位
- 既存walk-forward分布から説明可能な閾値

ただし本番データで未来情報を使わないよう注意する。

## 7. UI

カード表面には追加しない。

詳細ダイアログへ追加する。

第一候補:

```text
予報根拠度    高
```

必要なら補足:

```text
Trend・類似局面など予報材料の揃い具合
```

をdocsまたはhelp側へ置く。

現行:

```text
Trend信頼度（シグナル一致度・的中確率ではありません）
```

は残してもよいが、
詳細画面が冗長になる場合は、

```text
Trend一致度
```

へ短縮してよい。

ただし値の意味は変えない。

## 8. JSON

新規フィールド:

```json
{
  "forecast_support": 0.00
}
```

必要に応じて診断用に内部値を持つ。

JSONへ追加を検討してよい値:

```text
analog_effective_sample_size
```

ただし説明価値の低い中間値を大量に公開JSONへ追加しない。

既存:

- up_probability
- weather
- trend_probability
- analog_probability
- trend_confidence
- confidence
- analog_count
- analog_mean_distance
- range
- risk

の意味は変更しない。

## 9. prospective / 過去JSON

保存済みprospective forecastは書き換えない。

`forecast_support` が存在しない過去JSONはそのまま許容する。

scoring側が新フィールドを必須として壊れないようにする。

将来、prospective蓄積後に

```text
forecast_support別の実績
```

を調べられる構造にしておく。

## 10. docs

最低限更新:

```text
docs/forecast-values-guide.md
docs/forecast-algorithm.md
docs/TODO.md
```

必要なら:

```text
docs/market-weather-spec.md
```

を更新する。

説明では必ず:

- forecast_supportはup_probabilityを支える材料の強さ
- 的中確率ではない
- 上昇確率そのものではない
- weatherはup_probabilityから決まる
- forecast_supportはその元になる予報材料の質・整合性を見る

を明記する。

## 11. 触らないもの

今回変更しない:

- Trend probabilityの式
- Analog probabilityの式
- Trend / Analogの50:50 weight
- weather閾値
- range計算
- risk計算
- Yahoo取得
- Android Yahoo現在値取得
- live current更新
- 円換算
- 表示オプション
- riskの風表現
- セクター雨雲レーダー

本タスクは「上昇確率の根拠度」の追加に限定する。

## 12. テスト

最低限:

- forecast_supportが0〜1
- Trend/Analog一致時 > disagreement時
- Analog距離品質良 > 悪
- ESS高 > 低
- trend_confidence高 > 低
- 0.5境界跨ぎで不連続ジャンプしない
- Analogなしfallback
- forecast_support追加でup_probabilityが変わらない
- weatherが変わらない
- range/riskが変わらない
- forecast JSON同期先へ反映
- 過去JSONにforecast_supportがなくてもscoringが壊れない
- UI詳細で段階表示
- カード表面へ追加されない
- leak-safe回帰
- `python -m unittest discover -s tests -p 'test_*.py'`
- `git diff --check`

既知の無関係failureがある場合は切り分ける。

## 13. PRで必ず報告するもの

- 採用したforecast_support式
- 各構成要素と重み
- Analog qualityの定義
- ESSを採用したか
- Analogなし時の扱い
- walk-forwardでの市場別分布
- disagreement局面でのsupport例
- Analog品質弱/強のsupport例
- UI段階閾値の決め方
- 的中率との関係は参考値としてのみ報告
- test結果
- 変更ファイル
- 残課題

## 完了条件

- `forecast_support` が新しい独立指標として追加される
- up_probability / weather / trend_confidence / confidenceの意味を変更しない
- raw analog_count=30固定加点を使わない
- Trend/Analog disagreementを連続的に反映
- Analogの「質」と「実効サンプル量」を少なくとも検討
- 的中確率として表示しない
- UIは初期段階では低/中/高を基本とする
- カード表面へ追加しない
- branchへcommit/push
- PR作成
- mainへmergeしない

## 最後の報告

以下を報告する。

- Git運用: branch
- branch名
- commit SHA
- PR番号
- forecast_support式
- 各材料の意味
- walk-forward分布診断
- UI表示仕様
- test結果
- 変更ファイル
- 残課題
