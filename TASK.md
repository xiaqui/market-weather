# TASK.md

## 目的

Yahoo Finance から取得できる4市場の実データ現在値を、Market Weather の正本データから Web / Android まで実際に反映できる状態にする。

対象市場:
- 日経平均
- NYダウ
- USD/JPY
- GOLD

## 現状

- `scripts/fetch_market_data.py` で Yahoo Finance Chart API から4市場の現在値を取得できる。
- GitHub Actions の `Verify Market Data` で実接続成功済み。
- `scripts/sync_forecast.py` で `shared/forecast.json` から Android / Web へ同期できる。
- ただし現在、Pages / APK に入っている値は固定ダミー値のまま。
- PR #1「4市場の現在値取得を追加」が open。

## 今回やること

PR #1 の branch を最新 main に追従させたうえで、以下を実装する。

1. Yahoo Finance から4市場の現在値を取得する。
2. `shared/forecast.json` の `current` と `generated_at` を実データで更新する。
3. `python scripts/sync_forecast.py` を実行する。
4. 以下へ同じ値を反映する。
   - `android/app/src/main/assets/forecast.json`
   - `android/app/src/test/resources/forecast.json`
   - `web/forecast.json`
5. 既存UIは変更しない。
6. `up_probability`, `range_low`, `range_high`, `confidence`, `weather`, `risk` は今回は変更しない。
7. 実データ反映後の4市場の current を報告する。
8. テストと build を実行する。
9. `git diff --check` を実行する。
10. 問題なければ PR #1 の branch に commit / push する。
11. PR #1 を更新する。新しいPRは作らない。

## 注意

- main へ直接 push しない。
- 今回は定期更新の自動化までは行わない。
- 現在値取得に失敗した場合、固定ダミー値で上書きして成功扱いにしない。
- 4市場すべて取得成功した場合のみ正本JSONを更新する。
- 取得元は現状の Yahoo Finance Chart API をそのまま使う。
- Android / Web の表示仕様・デザインは触らない。

## 完了条件

以下がすべて満たされていること。

- 4市場の実現在値が取得できる。
- `shared/forecast.json` に実値が入っている。
- Android / Web 用JSONが正本と一致している。
- 単体テスト成功。
- Android build 成功。
- `git diff --check` 成功。
- PR #1 が最新commitに更新されている。

## 最後の報告

以下だけ報告する。

- 4市場の取得値
- 変更ファイル
- test/build結果
- commit SHA
- PR #1 の更新結果
- 残課題
