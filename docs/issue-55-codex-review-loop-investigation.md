# Issue #55: Codex レビュー自動修正ループ調査

調査日: 2026-10-14

## 結論

既存の ChatGPT / Codex Cloud 契約と GitHub Actions の `GITHUB_TOKEN` だけで、
「Codex レビューの P1/P2 検出 → Codex Cloud へ修正依頼 → 再レビュー」を完全自動化できる、
検証済みかつサポートされた経路は確認できなかった。このため、安全側に倒して workflow は追加しない。

特に、Actions が投稿した `@codex` コメントを Codex GitHub App が実装タスクとして受理するという
公開仕様は確認できない。GitHub 側にも `GITHUB_TOKEN` で作成されたイベントが通常は新しい
workflow run を起動しない再帰防止がある。Codex App が GitHub webhook をどう扱うかは別問題だが、
bot 投稿を受理するという契約がない以上、その挙動に依存する実装を「自動化完了」とは扱えない。

## 調査した現状

- 既存 workflow は APK build、Pages deploy、日次 forecast 更新、market data 検証の4本で、
  Codex/OpenAI API、レビューコメント処理、修正ループを行う workflow は存在しない。
- repository 内に `OPENAI_API_KEY` や Codex 実行用 credential を参照する処理はない。
- 現在の Cloud 認証は repository の clone/push/PR 操作には使えるが、Actions 設定、Actions secrets、
  workflow runs、Issue #55 の REST API 読み書きには必要な fine-grained permission がなく `403` となった。
  GitHub App installation の取得 API は GitHub App JWT 専用であり、通常のユーザートークンでは確認できない。
- GitHub Actions の公式仕様では、`GITHUB_TOKEN` が起こしたイベントは、明示された例外を除き
  新しい workflow run を作らない。再帰防止には有効だが、Codex Cloud 起動を保証するものではない。
- OpenAI の公開されている PR review 案内は、人が PR conversation から Codex に質問・修正を依頼し、
  結果を確認する手順を説明している。Actions bot の mention を無人修正トリガーとして保証していない。

参照:

- [GitHub: Triggering a workflow](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow)
- [GitHub: Events that trigger workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
- [GitHub: Secure use of `pull_request_target`](https://docs.github.com/en/actions/reference/security/securely-using-pull_request_target)
- [OpenAI: Review pull requests with Codex](https://help.openai.com/en/articles/20001552-review-pull-requests-with-codex)

## 実地検証の結果と限界

以下を repository と GitHub API に対して確認した。

| 確認項目 | 結果 |
| --- | --- |
| repository / remote / branch の確認 | `xiaqui/market-weather`、`origin` 設定済み |
| 既存 workflow の確認 | Codex review/fix loop なし |
| repository metadata / PR 一覧 | 取得成功 |
| Actions workflow run 一覧 | token permission 不足で `403` |
| Actions permission / secret metadata | token permission 不足で `403` |
| Issue #55 の取得・コメント | token permission 不足で `403` |
| GitHub App installation metadata | user token では取得不可 (`401`) |
| Actions bot による `@codex` 投稿 | 未実施 |

最後の項目は、検証用 workflow を default branch に置き、実際に run させる必要がある。
未検証の workflow を先に merge したり、既存 secret を流用したり、追加の PAT/App key を要求したりするのは
Issue #55 の制約に反するため実施しなかった。したがって、bot mention が Codex task を開始するとは主張しない。

## 要件ごとの判定

| 要件 | 判定 | 理由 |
| --- | --- | --- |
| P1/P2 のみ検出 | 部分的に実装可能 | Review API の author/id/body/commit SHA を allowlist と構造化 parser で検証できる |
| 最大3回・重複防止 | 実装可能 | PR label/comment marker または artifact ではなく repository外の durable state が必要 |
| Codex 修正依頼 | **現条件では未実現** | 無課金かつ bot 起点で保証された Codex Cloud API/イベントがない |
| 自動再レビュー | **現条件では未実現** | 同じ未検証 trigger に依存する |
| CI gate | 実装可能 | Checks API で head SHA の required checks を確認できる |
| fork/外部入力の防御 | 実装可能 | same-repository、trusted author、exact head SHA、read-only checkout を必須化できる |
| 自動マージ禁止 | 実装可能 | merge permission/API を workflow に与えない |
| 追加課金なし | 満たすため停止 | OpenAI API key や新規有料 key を作成・要求していない |

検出、回数管理、CI gate だけを作っても、中心となる修正タスク起動が未検証なので、最大3回の
「自動修正ループ」を満たしたことにはならない。また、PR comment は state database ではないため、
改ざんや削除も考慮せずに回数管理へ使うべきではない。

## 無課金で採用できる代替運用

当面は人を trust boundary に置く半自動運用を採用する。

1. Codex review の P1/P2 を人が確認し、指摘が現在の head SHA に対して有効か検証する。
2. PR conversation で人が `@codex` を付け、対象 finding、許可する変更範囲、テスト条件を明記する。
3. Codex の新PR/commitとテスト結果を人が確認する。
4. 最新 head SHA に対して再レビューする。
5. 最大3回で停止し、未解決時は人へ escalation する。
6. CI成功後も自動mergeせず、倫/人間が最終検収する。

GitHub Actions で追加費用なしに補助できる範囲は、P1/P2候補を検出して人へ通知し、
`codex-fix-needed` のような label を付けるところまでである。その workflow を将来追加する場合も、
次を満たす必要がある。

- `pull_request_review: submitted` を使い、base branch の信頼済み workflow のみ実行する。
- reviewer login / GitHub App identity、review ID、review commit ID、現在の head SHA を照合する。
- body 全文を shell、prompt、code として実行しない。P1/P2 marker の構造だけを parse する。
- fork PR、外部 collaborator、古い review、edited comment を修正起動対象にしない。
- permissions は `contents: read`, `pull-requests: write`, `issues: write` 以下に限定し、
  `contents: write`, `actions: write`, merge 権限、repository secrets を与えない。
- concurrency を PR 番号単位にし、review ID と head SHA の処理済み marker を検証する。
- 人が確認した後の `@codex` 投稿は人のアカウントから行う。

## 完全自動化を再評価できる条件

次のいずれかが、追加課金なしで利用できると公式に確認できた時点で再評価する。

1. Codex GitHub App が Actions bot の mention を受理すること、および必要な権限・rate limit・
   event delivery が公開仕様で保証される。
2. 既存 Codex Cloud 契約に含まれる、GitHub Actions 向けの認証済み task API が提供される。
3. repository owner が sandbox PR で bot mention の end-to-end test を明示的に許可し、
   task 作成、commit、再レビューまで GitHub 上で観測できる。

その場合も、最初は dry-run で review ID/head SHA の記録と通知だけを検証し、その後に
same-repository PR 限定、最大1回から段階的に有効化する。最大3回、自動merge禁止、CI gate は
解除不能な安全条件として維持する。
