# AGENTS.md

## 合言葉

ユーザーが「たすけt」と入力したら、以下を実行すること。

1. 現在位置と対象repoが一致しているか「repo指定の自動補正」に従って確認する。
2. repo直下の TASK.md を読む。
3. TASK.md の最新指示を確認する。
4. TASK.md の「Git運用」に明記された方式へ必ず従う。
5. Git運用を自分で再判定・上書きしない。
6. TASK.md の最新指示を実装する。
7. 必要なテスト・ビルド・lintを実行する。
8. 指定された Git 運用に従って commit / push する。
9. branch作業の場合はPull Requestを作成する。
10. 最後に以下を報告する。
   - Git運用（main直push / branch）
   - branch名（branch作業の場合）
   - commit SHA
   - PR番号（branch作業の場合）
   - test/build結果
   - repo補正の有無
   - 残課題

TASK.md が存在しない場合、または TASK.md に Git運用が明記されていない場合は、
勝手に別作業やGit運用の判断を始めず、その旨だけ報告する。

## repo指定の自動補正

ユーザーの指定repo、現在位置、TASK.md、AGENTS.md、git remote origin が一致しているか、
作業開始前に確認する。

確認対象:
- 現在開いているrepo
- repo直下の TASK.md の存在
- repo直下の AGENTS.md の存在
- `git remote get-url origin`
- TASK.md 内に対象repoの明記がある場合はその記載

明らかな誤指定で、正しいrepoが一意に特定できる場合は自動補正して作業を続行してよい。

自動補正してよい例:
- TASK.md / AGENTS.md / origin が同じrepoを指している
- ユーザー指定だけが別repoになっている
- 正しいrepo候補が1つしかない

補正した場合は、作業開始前に必ず次の形式で簡潔に報告する。

```text
repo指定を <誤指定repo> から <補正後repo> に補正しました。
```

以下の場合は自動補正しない。
- TASK.md と origin が別repoを指している
- 正しいrepo候補が複数ある
- TASK.md が複数repoで見つかり、どれが対象か一意に決められない
- AGENTS.md / TASK.md / origin の証拠が食い違っている
- 補正すると別プロジェクトの変更を誤って適用する可能性がある

自動補正できない場合は作業を止め、
どの情報が食い違っているかだけ報告する。
推測で別repoへ移動して作業しない。

## Git運用の決定者

Git運用は、作業開始前に倫が変更内容を確認して決定し、TASK.md に明記する。

論君 / Codex は Git運用の決定者ではない。
TASK.md に書かれた main直push / branch の指定をそのまま実行すること。

倫が判断する基準は以下。

### main へ直接 commit / push してよい変更

- 文言変更
- 表示位置、余白、サイズ、色などの軽微な表示調整
- docs の更新
- 実機確認だけで良否を判断できる局所的変更
- 既存ロジックに影響しない軽微な修正
- 問題発生時に影響範囲を特定しやすく、容易にrevertできる変更

main 直pushした変更は、ユーザーが実機検収する。

### branch を作成して作業する変更

- ゲームロジックや内部処理の変更
- 複数機能に影響する可能性がある変更
- 大規模リファクタリング
- 実験的変更
- CI / workflow / build 設定の変更
- データ構造や保存形式の変更
- 外部サービス / API / 認証 / 権限に関わる変更
- 影響範囲を事前に判断しにくい変更
- 複数日にまたがる可能性がある作業

branch の変更は、main へ merge する前にコード検収を行う。

倫が判断に迷う場合は branch を使用する。

## GitHub remote / push

push 前に `origin` が設定されていることを確認する。

`origin` が存在しない場合は、以下を設定する。

```bash
git remote add origin https://github.com/xiaqui/market-weather.git
```

その後、認証済みのGitHub接続を使ってpushする。

branch作業の場合は、専用branchをpushしてPull Requestを作成する。
main直pushの場合は、Pull Requestを作成しない。

`origin` 未設定だけを理由に作業を未完了にしない。

## Android build

Codex Cloud 環境に Android SDK / `ANDROID_HOME` / `ANDROID_SDK_ROOT` が無い場合、
Cloud内で無理にAndroid SDKを新規構築しない。

その場合は以下を実行する。

- Pythonテスト
- 必要なlint / syntax check
- `git diff --check`
- TASK.md で指定された Git 運用に従った commit / push
- branch作業の場合はPR作成

Androidの正式なbuild確認は、push後の GitHub Actions `Build Android APK` に任せる。

Cloud内でAndroid buildできなかったことだけを理由に作業を未完了にしない。
GitHub Actions の結果を最終報告に含めること。

## 完了後

ユーザーが「まじおk」と言っても、Codex側ではmergeしない。
merge判断と実行は別担当が行う。
