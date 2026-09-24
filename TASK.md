# TASK.md

## 種別

新規タスク

# 日次予報workflowのprospective採点エラー修正

## 目的

GitHub Actions `Update Daily Forecast` の Run #6 が、
prospective forecast採点ステップで以下のエラーにより失敗した。

```
ModuleNotFoundError: No module named 'scripts'
```

このエラーだけを確実に修正し、日次更新workflowが最後まで成功する状態に戻す。

## 現状

Run #6 では以下まで成功している。

- Fetch completed market data
- Sync forecast copies

その後、

- Score prospective forecasts

で失敗し、

- Commit updated forecasts

はskippedになった。

失敗箇所は `.github/workflows/update-daily-forecast.yml` から
`python scripts/score_live_forecast.py` を直接実行した際、
`scripts/score_live_forecast.py` 内の

```python
from scripts import fetch_market_data as market_data
```

が解決できなかったこと。

## 方針

できるだけ小さく直す。

第一候補はworkflow側の呼び出しを

```bash
python -m scripts.score_live_forecast
```

へ変更すること。

コード本体に不必要な `sys.path` 細工を入れない。

ただし、repo内の既存テスト・実行方法との整合を確認し、
より自然で副作用の少ない修正がある場合はそちらでもよい。

## 触らないもの

今回の修正では以下を変更しない。

- Trend / Analog / Ensemble の予報ロジック
- weather分類
- confidence / risk計算
- forecast JSONの意味
- prospective forecastの採点ルール
- scoring historyのスキーマ
- Web UI
- Android UI
- Android Yahoo現在値取得経路
- PR #26 のUI作業

## 確認事項

最低限以下を確認する。

1. `score_live_forecast` がrepo rootから正常に起動できる
2. 既存のprospective採点テストが成功する
3. daily workflow回帰テストが成功する
4. その他のPythonテストを壊していない
5. `git diff --check` が成功する
6. GitHub Actionsの `Update Daily Forecast` を再実行または新規実行し、
   Run #6で失敗した採点ステップを通過できることを確認する
7. forecast更新とscoring history更新が必要な場合、
   commit/pushステップまで正常に進むことを確認する

## GitHub運用

- main最新から新branchを作る
- mainへ直接pushしない
- 修正
- test
- commit
- push
- Pull Request作成
- mergeはしない

## 完了条件

- `ModuleNotFoundError: No module named 'scripts'` が再発しない
- `Score prospective forecasts` が成功する
- `Update Daily Forecast` workflowが最後まで成功する
- 予報ロジックやUIに不要な変更を入れていない
- tests成功
- `git diff --check` 成功
- 新PR作成済み
- mergeしていない

## 最後の報告

以下だけ報告する。

- branch名
- commit SHA
- PR番号
- 修正内容
- test結果
- Update Daily Forecast Actions結果
- 変更ファイル
- 残課題
