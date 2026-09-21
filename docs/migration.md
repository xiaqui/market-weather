# Market Weather 移植・構築記録

この文書は、Market Weather を最初のCloud生成物から
現在の `xiaqui/market-weather` へ移し、
GitHub Actions / Pages / Codex Cloud / WebView APK まで実際に動かした手順と知見を残す。

初期の「sandboxからコピーするための予定手順」ではなく、
実際に行った移植・復旧・運用確立の記録。

## 1. 初期生成

最初のAndroid / Web実装は Codex Cloud 側で生成した。

ただし当時のCloud環境ではGitHubへのpushが正常に通らず、
Cloudから直接repoへ反映できなかった。

さらにモバイルからのzip取得も安定しなかったため、
生成されたテキストファイル群を別途再構成し、
ローカルVAIOへ渡してGitHubへpushした。

最初の本体実装commit:

```text
2a6850dd99147e5e0fb3647113c83f1a2c1199e8
Add initial Market Weather Android and Web implementation
```

この時点で、

- Android
- Web
- shared/forecast.json
- Python同期スクリプト
- GitHub Actions雛形

がrepoへ入った。

## 2. Android APK workflow の復旧

初回のGitHub Actionsでは、
Gradle Wrapper関連が不足してAPK buildが失敗した。

対策として workflow 内でGradle Wrapperを生成するよう変更した。

commit:

```text
b86aab470f6a4480016416d8ee9904eacbb3da63
Generate Gradle wrapper in APK workflow
```

以後、GitHub Actions上でDebug APK生成が安定した。

知見:

- Cloud/ローカルでAndroid SDKが無くても、GitHub Actionsを正式build環境にすればよい
- Cloud内buildに固執しない
- Artifact名は固定する

現在のArtifact名:

```text
market-weather-debug
```

APK名:

```text
market-weather-debug.apk
```

## 3. GitHub Pages 有効化

Web版は `web/` を公開対象とし、
GitHub ActionsからPagesへdeployする構成にした。

Pages有効化commit:

```text
883c72e3ae61ffa3c097a053e8bf37bce472aeb8
Enable GitHub Pages from deployment workflow
```

公開URL:

```text
https://xiaqui.github.io/market-weather/
```

知見:

- Web表示の正本をPagesへ寄せると、iPhone / Windows / Androidで同じ画面を確認できる
- Android APKまで同じWebを表示する構成にすると二重UI保守をやめられる

## 4. Codex Cloud 環境のGitHub認証

Codex Cloud環境では、repo checkoutやpush状態が安定しない場面があった。

最終的に、Cloud環境のSecretとして `GITHUB_TOKEN` を登録し、
Setup Scriptで `gh auth login` と `gh auth setup-git` を実行する方式を採用した。

実績のあるSetup Script:

```bash
if [ -n "${GITHUB_TOKEN:-}" ]; then
    github_token="${GITHUB_TOKEN}"
    unset GITHUB_TOKEN

    echo "${github_token}" | gh auth login --with-token

    unset github_token
    gh auth setup-git
fi

git remote get-url origin >/dev/null 2>&1 ||
git remote add origin https://github.com/xiaqui/market-weather.git

git config user.name "Codex Cloud"
git config user.email "codex-cloud@users.noreply.github.com"
```

知見:

- Secretはsetup phaseで使う
- agent phaseではSecretそのものに依存しない
- `origin` が無い場合を想定して補完する
- `AGENTS.md` 側にもorigin復旧ルールを持たせる
- Android SDK不足は失敗扱いにせず、GitHub Actionsへ委譲する

## 5. AGENTS.md + TASK.md 運用

Cloudへ毎回長い指示文を貼らず、
repo内の `TASK.md` を論君が読む方式へ変更した。

`AGENTS.md` に、

```text
ユーザーが「たすけt」と入力したらTASK.mdを読む
```

という合言葉を定義。

以後、

```text
たすけt 実データ反映
たすけt baseline予測
たすけt WebView化
```

のように、
「合言葉 + 人間向け短いタイトル」だけでCloudタスクを起動する運用にした。

知見:

- `たすけt` だけだとCloud側タスク名が `help` や `typo` 等になり、一覧性が悪い
- 後ろに短い案件名を付けるとタスク名も読みやすくなる
- 実装指示はTASK.md、Cloud一覧名は短いタイトル、という役割分担が安定する

## 6. 実データ現在値の導入

Yahoo Finance Chart APIから4市場の現在値取得を追加した。

対象:

- 日経平均
- NYダウ
- USD/JPY
- GOLD

PR #1:

```text
4市場の現在値取得を追加
```

merge commit:

```text
7cb3306d36cc2fa65e1303775cb92041cae00be9
```

GitHub Actions上でYahoo Financeへの実接続も確認した。

知見:

- 4市場すべて取得成功した場合だけ正本JSONを更新する
- 外部API失敗時に中途半端な値を書かない
- 現在値取得とJSON同期を分離する

## 7. baseline予報の導入

次に、過去1年の日足からTrend baselineを実装した。

主な内容:

- 1/5/20日騰落率
- 5/20日移動平均乖離
- 5/20日ボラティリティ
- 上昇確率
- 予想レンジ
- confidence
- weather
- risk
- walk-forwardバックテスト

PR #2:

```text
初回Trendベースライン予報を実装
```

merge commit:

```text
8841b7840b7472549c0f8009a3c9a60472a627d9
```

### 未確定日足の罠

Codex Reviewで、
Yahooの日足レスポンスに市場営業中の「形成中の日足」が含まれることが指摘された。

そのまま使うと、

- 予測が取引中に変化する
- バックテスト最終サンプルが未確定足になる
- 翌営業日予報として不整合

になる。

対策:

- 確定日足と現在値を分離
- `currentTradingPeriod.regular` を見て進行中足を除外
- 表示用現在値は `regularMarketPrice` を別使用
- 回帰テストを追加

修正commit:

```text
fc57899b7395ea912efb146da636143ebba1a575
```

これは今後も重要な知見。

## 8. AndroidをWebViewカプセル化

当初のAndroid版はJetpack ComposeでWeb版と別UIを持ち、
APK内のforecast.jsonを読んでいた。

この方式だと、

- Web UI
- Android UI
- Web用JSON
- Android用JSON

を二重に保守する必要があった。

実機用途では同じ情報を表示できれば十分だったため、
Android本番版をGitHub Pagesを表示するWebViewカプセルへ変更した。

### 参照した実績コード

既存の `xiaqui/eiken2-webview` で実機成功済みの
`MainActivity.java` をモデルにした。

Cloudから別repoを参照できることを前提にせず、
実績済みMainActivity相当をTASK.md内へ直接埋め込み、
Market Weather用に以下だけ変更する方針にした。

- package
- START_URL
- 内部URL判定
- アプリ名

開始URL:

```text
https://xiaqui.github.io/market-weather/
```

applicationId:

```text
jp.xiaqui.marketweather
```

### Compose版の保全

WebView化前のCompose版は、

```text
native-compose
```

branchへ保全した。

通常開発はWebView版mainで進め、
必要な節目だけCompose版へ追従する。

### WebView化PR

PR #3:

```text
AndroidアプリをWebViewカプセル化
```

merge commit:

```text
96ac8a8497f64890d279c0b611f42533ac281868
```

実機で縦持ち・横持ちとも表示確認済み。

知見:

- 実績済みWebViewコードは再設計せず、必要最小限の変更で流用する方が安定する
- 別repo参照をCloudに要求するより、既知の実績コードをTASK内へ直接渡す方が一発で通りやすい
- WebView化後は通常の市場データ・予測・Web UI更新でAPK再build不要
- APK再buildが必要なのはURL、WebView設定、権限、アイコン等の「殻」を変える場合

## 9. Android 6 / Z3TCについて

既存 `eiken2-webview` は minSdk 23 でAndroid 6対応だが、
Z3TCではWeb表示が白画面になった実績がある。

そのためMarket WeatherではAndroid 6対応を必須条件にしなかった。

WebView化時は既存の minSdk 26 を維持。

知見:

- 「APKがインストール可能」と「WebViewで実際に表示可能」は別問題
- 古いAndroid対応は、実機WebView互換性まで含めて判断する

## 10. repo rename とCodex Cloud環境

別のCloud環境検証で、
GitHub repo `pygame01` を `pygame` へrenameした。

Cloud環境のSetup Script内URLを新repo名へ修正して保存すると、
Codex Cloud側の参照repo表示も `xiaqui/pygame` へ自動追従した。

知見:

- repo renameだけならCloud環境を必ずしも作り直す必要はない
- Setup Scriptの直書きURLは修正する
- all-repo権限のPATならtoken作り直しも不要だった
- まず小さな検証repoでrename追従を試すと安全

## 11. 現在の運用

現在の基本フロー:

```text
倫がTASK.mdを書く
    ↓
社長が論君へ「たすけt <短いタイトル>」
    ↓
Codex Cloudが実装 / test / branch / push / PR
    ↓
社長「みて」
    ↓
倫がPR / Actions / Reviewを確認
    ↓
実機確認
    ↓
社長「まじおk」
    ↓
倫が最新headとCIを再確認してmerge
    ↓
「でぷろいおk」
    ↓
Pages / Actionsのdeploy結果を確認
```

この流れを標準運用とする。

## 12. 現在の構成

```text
shared/forecast.json
        ↓
Python予測エンジン
        ↓
web/forecast.json
        ↓
GitHub Pages
        ↓
Android WebView APK
```

表示の正本はWeb版。

Composeネイティブ版は `native-compose` branch に保全。

## 13. 今後の移植・テンプレ化

用途別のCodex Cloud工房を少しずつ増やす方針。

候補:

- pygame
- webview-capsule
- android-lab
- static-web
- game-lab

Cloud環境はrepo指定が必須なので、
用途別テンプレrepoを「作業工房」とし、
そこで案件を完成させてから個別repoへ引っ越す方式を想定する。

実績のあるコードと手順をテンプレ側へ蓄積し、
同じ罠を案件ごとに踏み直さないことを目的とする。
