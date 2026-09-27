# Target-specific weather map v1（研究レポート）

## 結論

これは探索的比較であり、**本番採用はしない**。現行 forecast のコード、JSON、
weather 閾値、日次 workflow は変更していない。既存研究ですでに観測した期間を
含むため、この結果だけでモデルを選ばず、固定した実装を将来の未使用 252
session window で再評価する。

v1 の有力候補は USDJPY と GOLD である。USDJPY は target-specific Analog が
直近 discovery を含む全 5 window で common Analog より高 accuracy、低 Brier
だった。GOLD は全 window で Brier が改善し、5 window 中 4 window で accuracy
も改善した。一方、DOW は一貫して accuracy が悪化したため common を維持する。
NIKKEI も validation 4 window 中 3 window で accuracy と Brier が悪化しており、
現行 common を維持する。

完全な機械可読結果は
[`reports/target-specific-weather-map-v1.json`](../reports/target-specific-weather-map-v1.json)
に保存した。各 window は 252 session、各市場 1,260 aligned sample で、window 0
を discovery、過去側 4 本を exploratory validation とした。

## 市場別材料

| target | Yahoo symbol | 経済的役割 |
|---|---|---|
| NIKKEI | `^DJI`, `JPY=X`, `GC=F` | 米株、円相場、金 |
| DOW | `^VIX`, `^IXIC`, `^TNX` | リスク回避、成長株、米金利 |
| USDJPY | `DX-Y.NYB`, `^TNX`, `^N225` | ドル全体、米金利、日本株 |
| GOLD | `DX-Y.NYB`, `^TNX`, `^VIX` | ドル全体、米金利、リスク回避 |

各材料から 1/5/20 日 return、20 日移動平均乖離、5 日対 20 日 volatility 比の
5 feature（計 15 feature）を作る。target ごとにこの 3 symbol だけを選ぶ。

## 時系列・欠損ポリシー

- Yahoo Chart API の形成中の日足は既存 parser で除外する。
- Yahoo の日付 label は、追加した米国 symbol について保守的な close 時刻
  （VIX/NASDAQ/TNX は New York 16:00、DXY は 17:00）へ変換する。
- target の次回 close より厳密に前の global clock を選び、各材料を as-of join
  する。未来の材料 row と、query 時点でまだ判明していない Analog outcome は
  候補から除外する。
- 休場または単発欠損は、捏造や未来方向の補間をせず、最後に完了した実 row を
  使用する。いずれかの材料が 21 observation 未満ならその state を skip する。
- 追加 symbol の取得と評価は独立 script 内だけで行うため、取得失敗は本番
  forecast に影響しない。

## 結果要約

以下は target-specific の common 比（Analog 単体）。括弧内は discovery を含む
5 window 中の改善 window 数である。

| target | discovery accuracy | discovery Brier | validation の傾向 | 判断 |
|---|---:|---:|---|---|
| NIKKEI | 55.95% vs 57.94% | .2468 vs .2479 | accuracy 1/4、Brier 1/4 改善 | common 維持 |
| DOW | 51.59% vs 55.16% | .2512 vs .2565 | accuracy 0/4、Brier 1/4 改善 | common 維持 |
| USDJPY | 61.90% vs 51.19% | .2266 vs .2522 | accuracy 4/4、Brier 4/4 改善 | prospective 候補 |
| GOLD | 59.52% vs 56.35% | .2367 vs .2530 | accuracy 3/4、Brier 4/4 改善 | prospective 候補 |

JSON には各 model の direction accuracy、Brier、Trend と Analog の不一致時勝率、
always-up/down・constant-50・expanding historical-rate の naive baseline、sample
count を window ごとに収録している。50:50 Trend Ensemble も併記したが、Analog
の改善が Ensemble に薄められる市場があるため、重みは今回調整していない。

## 次の改善候補

- **NIKKEI:** common を維持。`GC=F` の除外 ablation と、米国成長株または VIX
  への入替を次回候補にする。
- **DOW:** common を維持。3 材料 v1 は採用候補にしない。`^IXIC` と DOW の
  冗長性を ablation で確認し、credit spread / dollar 系の別役割を検討する。
- **USDJPY:** v1 を凍結して prospective 評価へ進める。`^N225` の寄与を
  leave-one-material-out で確認し、Asia/US close の clock 別集計も行う。
- **GOLD:** v1 を prospective 候補にする。`^VIX` の寄与と、real-yield proxy
  への入替を比較する。
- **全市場:** 材料を見てから同じ window に最適化しない。次の 252 session を
  untouched holdout とし、symbol 欠損率・staleness 別の成績も事前登録する。

## 再実行

```bash
python scripts/validate_target_specific.py
```

外部データ取得に失敗した場合は script が失敗して report を更新しない。本番
forecast generator からこの script を呼ばないことが、その障害分離である。
