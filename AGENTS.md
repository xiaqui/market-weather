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

## GitHub remote / push

push 前に `origin` が設定されていることを確認する。

`origin` が存在しない場合は、以下を設定する。

```bash
git remote add origin https://github.com/xiaqui/market-weather.git
```

その後、認証済みのGitHub接続を使って専用branchをpushし、Pull Requestを作成する。

`origin` 未設定だけを理由に作業を未完了にしない。

## Android build

Codex Cloud 環境に Android SDK / `ANDROID_HOME` / `ANDROID_SDK_ROOT` が無い場合、
Cloud内で無理にAndroid SDKを新規構築しない。

その場合は以下を実行する。

- Pythonテスト
- 必要なlint / syntax check
- `git diff --check`
- commit / push / PR作成

Androidの正式なbuild確認は、push後の GitHub Actions `Build Android APK` に任せる。

Cloud内でAndroid buildできなかったことだけを理由に作業を未完了にしない。
GitHub Actions の結果を最終報告に含めること。

## 完了後

ユーザーが「まじおk」と言っても、Codex側ではmergeしない。
merge判断と実行は別担当が行う。
