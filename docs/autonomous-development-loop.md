# 自走開発ループ運用ガイド

更新: 2026-09-29

## 1. 目的

この文書は、Market Weather で実際に行った「ChatGPTがGitHub上の状態を読み、Codexへ実装を渡し、成果を検収し、安全ならmergeし、次の作業へ進む」自走開発ループから得た知見を、他プロジェクトへ移植できる形で整理する。

特定repoの実装仕様ではなく、TASK.md、PR、Codex、テスト、レポート、人間による実機確認をどう分担すると安全に自走できるかを扱う。

基本原則は次の通り。

1. 自走とは「勝手に変更すること」ではなく、事前に定義した境界内で判断と作業を連鎖させること。
2. 実装担当と検収担当を分ける。Codexの完了報告をそのままmerge条件にしない。
3. GitHubの現在状態を毎回読み直す。会話中の古い状態を事実として扱わない。
4. 自動判定可能なものは自動化し、実機・美観・プロダクト判断は人間へ残す。
5. 研究・実験では「改善した」ことと「本番採用してよい」ことを分離する。

---

## 2. 今回成立した自走ループ

実際に成立した流れは以下。

```text
TASK.md / HANDOFF / TODO / PR / reports を読む
        ↓
現在のGitHub状態を確認
        ↓
Codexの成果を検収
        ↓
問題あり
  → 同じ目的なら既存タスクへの追加修正としてPR上で @codex
        ↓
Codexが修正・test・push
        ↓
最新headを再取得して検収
        ↓
競合などGit上の問題を検出
        ↓
Codexへ最新main追従を依頼
        ↓
新branchになった場合は実際のbranch/commitを確認
        ↓
必要ならPRを作成
        ↓
差分・テスト・本番非変更条件を再確認
        ↓
merge
        ↓
旧PRを置換済みとしてclose
        ↓
次タスクへ
```

重要なのは、会話上の「終わった」「直した」ではなく、GitHubのhead SHA、diff、test結果、mergeable状態を正本にしたこと。

---

## 3. 成功した点

### 3.1 TASK.mdを実装契約として使えた

TASK.mdに以下を明示すると、実装担当へ渡した後の自由度を適切に制限できた。

- タスク種別
- Git運用（main直push / branch + PR）
- 目的
- 変更対象
- 触らないもの
- テスト
- 完了条件
- 実機確認が必要な点

特に「触らないもの」が有効だった。研究コード追加時に本番forecastを変更しない、UI修正時に予測ロジックを変更しない、といった負の要件は、AI実装でスコープ膨張を防ぐ。

### 3.2 実装と検収を分離できた

Codexは実装・テスト・commit/pushを担当し、別の検収側が以下を確認した。

- 最新head SHA
- PR差分
- TASK適合性
- テスト結果
- report内容
- mergeability
- 本番ファイルへの意図しない変更

これにより「Codexが完了と書いたのでmerge」という危険な一段飛ばしを避けられた。

### 3.3 追加修正を新規タスク化しすぎなかった

同じ目的の修正は「既存タスクへの追加修正」として同じPR文脈で扱った。タスクの意味とGit branchの都合を分離した点が重要。

```text
目的が同じ → 既存タスクの続き
目的が別   → 新規タスク

branchが変わった / merge済み
≠ 自動的に新規タスク
```

この区別により、履歴が「何を達成しようとしていたか」で追える。

### 3.4 時系列モデルで未来リークをmerge前に止められた

target-specific weather map実験では、見た目の成績だけでなく、forecast clockと前回target closeの境界をレビューした結果、材料欠損時にTrend側がforecast clockより未来のcloseを参照できる可能性を検出した。

修正後は概念的に、

```text
max(使用material時刻, 前回target close)
<= forecast clock
< target outcome
```

を保証し、境界ケースを回帰テストへ追加した。

これは一般化すると、「モデル評価では精度より先に情報利用可能時刻を検証する」という教訓になる。

### 3.5 exploratory と production adoption を分離できた

USDJPY / GOLDでtarget-specific版が複数windowにわたり改善しても、そのwindowをすでに見ているため即採用しなかった。

- 観測済みwindow: exploratory
- 未使用holdout: out-of-sample
- 将来蓄積: prospective
- 本番採用: untouched OOS / prospective確認後

AIは数字が改善すると嬉々として採用したがる。人間も大差ないので、制度で止める必要がある。

### 3.6 競合を「merge失敗」ではなく次の作業として処理できた

PRが `mergeable_state: dirty` になった際、無理にmergeせず最新main追従をCodexへ戻した。

競合解消後も、元PRが更新されたと決めつけず、実際には新branch `codex/merge-main-target-safety` と新commitが作られていることを確認した。新PRを作り、merge後に旧PRを「置換済み」と記録してcloseした。

Gitの形が想定と違っても、目的・差分・履歴を保って回復できた点は成功。

---

## 4. 失敗した点

### 4.1 古い状態を見て「未完」と判断した

最大の失敗は、Codexがすでに修正を終えていたのに、古いレビュー状態を基準に「まず修正を投げる」と判断しかけたこと。

原因:

- 会話中に保持していた状態を最新とみなした
- PRの最新comment / head SHA確認を先にしなかった
- 「直前に見た情報だからまだ有効」という人間的で雑な前提を置いた

改善策:

```text
状態依存の判断前には必ず再取得:
- PR state
- head SHA
- updated_at
- recent comments
- mergeable
```

「さっき確認した」はキャッシュであり、GitHubの事実ではない。

### 4.2 Codexへの競合解消依頼が元PR更新にならなかった

「このPRブランチへ最新mainを取り込む」と依頼したが、Codexは別branchを作成した。

結果自体は回収できたが、自走ループとしては余計な分岐が発生した。

改善策:

- 依頼時に対象branch名を明記する
- 「新branch/新PRを作らず、このbranchへpush」と明記する
- ただし権限・実行環境上それが不可能な場合に備え、別branchを許容する回復手順も持つ

### 4.3 「完了したら検知する」と言い切るのは危険

通常チャットはバックグラウンド常駐監視ではない。ユーザーから再度呼ばれた時点でGitHubを再確認することはできるが、何もトリガーがないまま継続監視して自発的に報告するわけではない。

したがって表現と設計を分ける。

- 対話型: ユーザーの次メッセージ時に再確認して続行
- 自動監視型: webhook / automation等、明示的なトリガーを用意

「自走開発」と「常時監視」は別機能。

### 4.4 full test failure の扱いが曖昧になりやすい

target-specificの対象テストは通っていた一方、full suiteには既知failureやmain由来UI failureが存在した。

「今回と無関係」と実装担当が報告しただけではmerge根拠として弱い。

最低限、

- mainでも同じfailureが出るか
- 変更ファイルとfailureの依存関係
- failure数が増えていないか
- target testが通るか

を区別する必要がある。

既知failureは永遠の免罪符ではない。放置すると、いつの間にか「赤いのが普通」という文明末期のCIになる。

---

## 5. 注意点

### 5.1 毎回最新headを基準にする

検収対象はPR番号ではなく「PRの最新head SHA」。

レビュー済みSHAと現在headが違えば、原則として再検収する。

merge時には可能なら expected head SHA を指定し、検収後にheadが動いた場合はmergeを失敗させる。

### 5.2 Codexの報告とGitHub実体を分ける

報告:
```text
tests passed
production unchanged
branch pushed
```

検収:
```text
実際のheadは何か
変更ファイルは何か
mainとの差分は何か
PRはmergeableか
production fileに差分はないか
```

報告は証言、GitHubは現場。

### 5.3 UIの最終判断は自動mergeしない

CSS testが通っても、

- 視覚的な重心
- 実機WebView差
- 狭い画面での印象
- タップ感
- 「なんか右すぎる」

はテストで完全には決められない。

したがってUIタスクでは、

```text
コード上の安全性 → 自動検収可能
実機上の良否     → 人間確認
```

と境界を明記する。

### 5.4 research-onlyコードは本番経路から物理的に分離する

実験script、report、testを本番forecast生成経路から分離する。追加symbol取得失敗が本番更新を壊さない構造にする。

「本番では呼ばないつもり」より「import / workflow経路に入っていない」の方が強い。

### 5.5 レポート生成時刻もデータ境界

日足が存在していても、evaluation timestamp時点でまだ確定していないoutcomeを評価へ入れてはいけない。

report generation timestampを固定し、それより未来に確定するrowを除外する。再実行で最新確定rowが増えれば数値が変わることもreportへ明記する。

### 5.6 reportの数字だけでなくsample countを見る

accuracyやBrier改善だけでなく、

- paired sample count
- windowごとの件数
- common / candidateで同じtimestamp・actualを比較しているか
- 欠損で片側だけ有利になっていないか

を確認する。

比較前にintersectionを作り、同じpaired rowsからwindowを切るのが安全。

---

## 6. 他プロジェクト向け推奨構成

repo root:

```text
AGENTS.md
TASK.md
docs/HANDOFF.md
docs/TODO.md
docs/autonomous-development-loop.md
```

役割:

### AGENTS.md
実装担当が常に守るrepo規約。テスト、禁止事項、Git操作など。

### TASK.md
「今やること」の正本。一度に主タスクを増やしすぎない。

### HANDOFF.md
現在の設計、重要な経緯、壊してはいけない前提。

### TODO.md
長期バックログ。今すぐCodexへ渡す指示書ではない。

### autonomous-development-loop.md
人間・検収AI・実装AIの役割と自走ルール。本書。

---

## 7. 推奨TASKテンプレート

```md
# タスク名

種別:
- 新規タスク / 既存タスクへの追加修正 / 再実行 / 完了処理

Git運用:
- main直接push / branch + PR

## 背景
なぜ必要か。

## 目的
何が成立すれば成功か。

## 変更対象
触ってよいファイル・機能。

## 触らないもの
本番ロジック、API、UIなど明示。

## 実装要件
具体的な要件。

## テスト
target test
full suite
syntax/lint
git diff --check

## 完了条件
客観的に判定できる条件。

## 人間確認
実機、美観、業務判断など自動判定しない項目。
```

---

## 8. 自走側の標準チェックリスト

### 作業開始前

- mainの最新SHA確認
- open PR確認
- TASK.md確認
- HANDOFF / TODOとの矛盾確認
- 既存作業の続きか新規か判断
- Git運用決定

### Codex完了後

- PR最新head SHA取得
- recent comments確認
- changed files確認
- TASKの「触らないもの」違反確認
- target test確認
- full suite確認
- diff check確認
- report / artifact確認
- mergeability確認

### merge直前

- headが検収時から動いていない
- baseが想定branch
- merge conflictなし
- 本番に意図しない差分なし
- 人間確認待ち項目がない
- expected head SHA付きmergeを優先

### merge後

- mainへ入ったことを確認
- 置換された旧PRを整理
- TASK / HANDOFF / TODOの更新要否を確認
- 次タスクを開始する前に現在地を再取得

---

## 9. 自動で進めてよい範囲

原則として自走可能:

- docs
- 明確な回帰テスト追加
- isolated research code
- test failure原因調査
- 既存仕様を変えないbug fix
- merge conflict解消（意味的競合がない場合）
- report再生成
- 完了済みPR整理

止めるべき例:

- UIの見た目の最終決定
- 仕様変更
- 本番モデル採用
- destructive migration
- credential / permission変更
- 課金を伴う操作
- データ削除
- 複数の妥当な設計案からプロダクト方針を選ぶ場面

「技術的にできる」と「勝手に決めてよい」は別。

---

## 10. 研究・ML系プロジェクト固有の追加ルール

### 10.1 時系列ではrandom splitを安易に使わない

未来の情報が過去へ混ざらないwalk-forward / non-overlapping validationを優先する。

### 10.2 データのtimestampとavailability timestampを分ける

市場データ、ニュース、決算、センサー値などは「その時刻を表す」ことと「その時刻に利用可能だった」ことが一致しない場合がある。

モデル入力にはavailabilityを使う。

### 10.3 同じValidationを見て改良を繰り返したら、それはDiscoveryになる

名前がvalidationのままでも、人間が結果を見て材料選択や重み調整に使った時点で実質的にtraining/discovery側へ移る。

新しいholdoutまたはprospective評価を用意する。

### 10.4 accuracyだけで判断しない

確率予測ならBrier Score等のcalibrationを含む指標、naive baseline、sample count、条件別性能も見る。

### 10.5 「候補」と「採用」をTASK上でも別状態にする

```text
experiment
→ candidate
→ untouched validation
→ prospective
→ production adoption
```

一つのPRで全部進めない。

---

## 11. 今後の課題

### 11.1 完了検知の仕組み

対話再開時のpull型確認だけでなく、GitHub PR更新やCodex完了をトリガーに検収ループを起動できれば、本当の意味で待ち時間まで自走できる。

候補:

- GitHub webhook
- automation
- CI完了イベント
- PR commentイベント

ただし無限ループ防止のため、1タスクあたりの再試行回数、同一failureの連続回数、停止条件が必要。

### 11.2 failure baselineの機械化

「既知failure」を文章で覚えるのではなく、mainのtest結果とPRのtest結果を比較し、

```text
new failures = PR failures - main failures
```

として新規failureだけをブロックできると安全。

ただしmainの赤を恒久放置しないよう、既知failure自体は別タスクで減らす。

### 11.3 TASK.mdの肥大化

完了タスクを追記し続けるとTASK.mdが履歴書になる。現在タスクの正本としては読みづらくなる。

推奨:

- TASK.md: 現在作業
- docs/task-history/: 完了タスク
- HANDOFF: 現在の重要仕様だけ

へ整理する。

### 11.4 PR置換ルールの明文化

Codexが別branchを作った場合の標準処理を定義する。

```text
1. 新branchと元branchの差分確認
2. 新branchが最新main基準か確認
3. 新PR作成
4. 検収
5. merge
6. 旧PRへ置換先をコメント
7. 旧PR close
```

### 11.5 自走レベルをタスクごとに指定する

例:

```text
AUTO-0: 調査のみ
AUTO-1: 実装・PR作成まで
AUTO-2: 検収し安全ならmergeまで
AUTO-3: merge後、次の明確なTASK作成・Codex投入まで
HUMAN: 実機/仕様判断で停止
```

これをTASK.mdへ書けば、「どこまで勝手に進めてよいか」が会話依存にならない。

---

## 12. 推奨する停止条件

自走ループは以下で停止する。

- TASKの目的が曖昧
- headが予期せず変更
- 新規failure発生
- security / credential / permission問題
- 本番データ破壊可能性
- migrationが不可逆
- 実機判断が必要
- exploratory結果からproduction採用へ移る判断
- 同じ修正を2回以上繰り返しても改善しない
- Codexの報告とGitHub実体が一致しない

止まることは失敗ではない。安全境界で止まれない自走の方が失敗。

---

## 13. この方式の完成形

理想形は、人間が毎回GitHubの交通整理をするのではなく、

```text
人間
  ↓ 目的・仕様・実機判断
検収/オーケストレーション
  ↓ TASK作成・状態確認・レビュー・merge判断
実装エージェント
  ↓ code / test / PR
GitHub / CI
  ↑ 状態・差分・test結果
```

という役割分担。

人間は「何を作るか」と「実物として良いか」に集中し、AI側は「実装 → 検証 → Git整理 → 次の明確な技術作業」を回す。

Market Weatherで今回確認できたのは、少なくとも branch + PR のロジック変更について、途中の未来リーク検出、追加修正、競合解消、PR置換、mergeまでをこの方式で繋げられること。

同時に、最新状態の再取得を怠ると一瞬で古い仕事をもう一度始めることも確認した。自走に必要なのは勢いではなく、毎ステップで正本へ戻る習慣である。
