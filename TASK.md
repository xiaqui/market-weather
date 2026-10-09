# TASK.md

## 種別
新規タスク

# prospective自動答え合わせ停止の修復

## Git運用
branch + PR

## 調査で確定した停止原因

日次workflow自体は正常に動いており、2026-10-03の Update Daily Forecast run #19 でも fetch / sync / score / commit は全step success。
停止しているのはworkflowではなく入力データの蓄積。

`scripts/score_live_forecast.py` は `reports/live-forecast/*.json` だけを採点するが、日次workflowには新しいimmutable forecast snapshotを作るstepがない。
`scripts/sync_forecast.py` も配布用3コピーだけで、prospective snapshotは保存しない。
さらにworkflowのcommit判定/ git add に `reports/live-forecast/*.json` が含まれない。
そのため最初に手動保存したsnapshotだけを毎日再走査し、historyは4件のまま増えなかった。

## 目的

毎日の本番forecastを生成した時点でimmutable snapshotとして保存し、後日の確定足取得時に自動採点する。再実行してもsnapshot/historyを重複させない。

## 実装要件

1. 本番 `shared/forecast.json` 生成後、採点前に、その時点のforecastを `reports/live-forecast/` へimmutable保存する専用処理を追加する。
2. snapshotには最低限 `source_generated_at` と当時のforecast payloadを保持し、既存 scorer が読める形式にする。
3. ファイル名は再実行で同一予報を重複保存しない決定的なものにする。既存snapshotは書き換えない。
4. 同じgenerated_atのsnapshotが既にあれば内容一致を確認してno-op。内容が異なる場合は黙って上書きせず失敗させる。
5. workflow順序は fetch -> sync -> snapshot保存 -> score -> commit とする。
6. workflowのdiff判定/git addに `reports/live-forecast/*.json` を含め、新規snapshotもmainへcommitする。
7. scorerは過去の未採点snapshotを毎回走査し、対象営業日の確定足が存在した時だけhistoryへ追加する。既存のidempotenceを維持する。
8. historyに ensemble の Brier contribution `(p-y)^2` を保存する。可能ならTrend/Analogも確率がある場合は同様に保存する。既存recordとの後方互換を壊さない。
9. flat outcomeの扱いを明記し、direction accuracy/Brierを不正に有利にしない。
10. 本番予測ロジック、weather閾値、モデル重み、UIは変更しない。

## 回帰テスト

- snapshot新規作成
- 同じgenerated_atの再実行はno-op
- 同名で内容不一致なら上書き拒否
- forecast日にはtarget未確定でwaiting
- 後日の確定足で採点される
- scorer再実行でhistory重複なし
- 4市場で異なるnext_session_date/休場を処理
- 複数日分snapshotを順次採点
- Brier計算
- workflowがsnapshotをscore前に保存しcommit対象に含める
- unit suite / py_compile / git diff --check

## 完了条件

- 新規forecastが日次でimmutable snapshot化される
- 後日自動で答え合わせがhistoryへ積まれる
- rerunしても重複しない
- workflow成功なのにhistoryだけ止まる今回のsilent failureを回帰テストで検知できる
- 本番forecastの値は変更しない
- PRで原因、変更点、test結果を報告する
