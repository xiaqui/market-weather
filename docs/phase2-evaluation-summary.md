# 金融天気図 検証フェーズ2 評価サマリー

## 目的

PR #5「金融天気図の非重複期間検証フェーズ2」で得られた結果を、今後の設計判断用に短く整理する。

最新252セッションはDiscovery期間であり、その前の非重複252セッション×4をValidationとして使用した。

評価対象は Trend / Analog / Ensemble に加え、以下のnaive baseline。

- always-up
- always-down
- constant 50% probability（Brier = 0.25）
- expanding historical up-rate（各予測時点以前の上昇率のみを使用）

## 全体評価

### 日経平均

現時点でもっとも強い結果。

Validation 4期間すべてで以下を満たした。

- Analog accuracy > Trend: 4/4
- 不一致時 Analog accuracy > Trend: 4/4
- Analog Brier < Trend: 4/4
- Analog accuracy > always-up / always-down: 4/4
- Analog Brier < 0.25: 4/4
- Analog Brier < expanding historical up-rate: 4/4

Validation各期間の方向精度:

| 期間 | 実際の上昇率 | Trend | Analog | Ensemble |
| --- | ---: | ---: | ---: | ---: |
| 2024-08-27〜2025-09-05 | 53.6% | 47.6% | 57.9% | 49.2% |
| 2023-08-17〜2024-08-26 | 53.2% | 48.0% | 65.5% | 54.8% |
| 2022-08-08〜2023-08-16 | 55.2% | 48.8% | 65.5% | 56.3% |
| 2021-07-28〜2022-08-05 | 52.8% | 50.4% | 60.3% | 53.6% |

TrendとAnalogが不一致だった時も、Analog優位が4期間すべてで再現した。

- 2024-25: Trend 38.8% / Analog 61.2%
- 2023-24: Trend 32.8% / Analog 67.2%
- 2022-23: Trend 34.1% / Analog 65.9%
- 2021-22: Trend 38.9% / Analog 61.1%

paired exact binomial p-valueも各期間でAnalog側優位。

- 0.0199
- 0.000125
- 0.000323
- 0.0235

現時点では、単にTrendが弱い・上昇相場だった・50%より少し良かった、では説明しにくい。

慎重な表現としては、

> 金融天気図は、少なくとも日経平均について、複数の非重複過去期間で単純baselineを上回る予測情報を持っている兆候が強い。

と評価する。

### NYダウ

Analogが効く期間はあるが、日経ほど安定していない。

- Analog accuracy > Trend: 3/4
- 不一致時 Analog accuracy > Trend: 3/4
- Analog Brier < Trend: 4/4
- Analog accuracy > always-up / always-down: 2/4
- Analog Brier < 0.25: 2/4
- Analog Brier < expanding historical up-rate: 2/4

Trendより良いことは多いが、単純な市場上昇バイアスを明確に超える期間は半分程度。

### USD/JPY

方向精度は混在するが、確率予測としてはTrendより改善する期間が多い。

- Analog accuracy > Trend: 2/4
- 不一致時 Analog accuracy > Trend: 2/4
- Analog Brier < Trend: 4/4
- Analog accuracy > always-up / always-down: 1/4
- Analog Brier < 0.25: 3/4
- Analog Brier < expanding historical up-rate: 1/4

Analog単独を主役にする根拠は弱い一方、Ensembleが良い期間があり、Trendとの混合に意味がある可能性が残る。

### GOLD

現時点では最も弱い。

- Analog accuracy > Trend: 2/4
- 不一致時 Analog accuracy > Trend: 2/4
- Analog Brier < Trend: 4/4
- Analog accuracy > always-up / always-down: 1/4
- Analog Brier < 0.25: 1/4
- Analog Brier < expanding historical up-rate: 1/4

Trendより確率がマシなことはあるが、単純baselineを安定して超えておらず、独立した予測力があるとはまだ言いにくい。

## 市場ごとの現時点の役割仮説

- 日経平均: Analogが主役候補
- NYダウ: Analog有効期間あり、まだ不安定
- USD/JPY: Analog単独よりEnsemble候補
- GOLD: 現状は補助情報レベル

これは現時点の検証結果から見える役割仮説であり、本番ロジックへ即反映する決定ではない。

## 解釈上の重要点

### 1. Trendより良いだけでは不十分

比較相手が弱ければ、Trendに勝つだけでは予測力の証明にならない。そのためnaive baselineを追加した。

### 2. 日経の結果はnaive baselineでも残った

日経は4つのValidation windowすべてで、方向精度でもBrierでも単純baselineを上回った。

### 3. USDJPY / GOLDは市場固有要因が強い可能性

USDJPYは政策・金利・介入観測、GOLDは実質金利・ドル・地政学・中央銀行買いなど、現在の4市場だけでは捉えにくい要因が相対的に強い可能性がある。

これは現時点では仮説であり、追加データで確認する。

### 4. まだ未来の前向き検証ではない

今回のValidationはDiscoveryと重複しないが、すべて過去データを遡ったretrospective validation。

本当の意味でのprospective validationは、2026-09-21以降の予報を事前保存し、次営業日以降に答え合わせする形で行う。

最初の保存済み予報:

`reports/live-forecast/2026-09-21.json`

今後は後から予報値を差し替えず、保存時点の値で判定する。

## 次の研究方向

- prospective validationを継続する
- 日経について国内セクター構造へ分解する
- 市場ごとに最適な役割が異なるか確認する
- Analog / Trend / Ensembleの重み変更は、前向き検証が蓄積するまで急がない
- 警報・注意報系は方向予報と分けて検証する

## 現時点の一文要約

金融天気図は4市場すべてで同じように効くわけではないが、日経平均では複数の非重複期間とnaive baseline比較を通して、他市場との配置情報に実用候補となる予測シグナルがある可能性が最も強く示されている。