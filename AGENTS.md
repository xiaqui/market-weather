# AGENTS.md

## 合言葉

ユーザーが「たすけt」と入力したら、以下を実行すること。

1. repo直下の TASK.md を読む。
2. TASK.md の最新指示を実装する。
3. 必要なテスト・ビルド・lintを実行する。
4. main へ直接pushしない。
5. 専用branchへcommitする。
6. GitHubへpushする。
7. Pull Requestを作成する。
8. 最後に以下だけ報告する。
   - branch名
   - commit SHA
   - PR番号
   - test/build結果
   - 残課題

TASK.md が存在しない場合は、勝手に別作業を始めず、その旨だけ報告する。

## 完了後

ユーザーが「まじおk」と言っても、Codex側ではmergeしない。
merge判断と実行は別担当が行う。